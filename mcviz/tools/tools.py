import re
from new import classobj

from logging import getLogger; log = getLogger("mcviz.main")

tool_types = {}
tool_classes = {}

class ArgParseError(Exception):
    pass

class ToolParseError(ArgParseError):
    def __init__(self, tool, msg, exc = None):
        self.tool = tool
        self.original_exception = exc
        new_msg = "%s %s: %s" % (tool._type, tool._name, msg)
        super(ToolParseError, self).__init__(new_msg)

class Arg(object):
    def __init__(self, name, converter, doc, default=None, choices=None, web=True):
        """<converter> can be float, int, str, or even a function
        WARNING: Any function put in here will receive a user input string
        and must treat the string as TAINTED"""
        self.name = name
        self.converter = converter
        self.doc = doc
        self.default = default
        self.choices = choices
        self.web = web

def tool_type_options():
    res = []
    for tool_type in sorted(tool_types.keys()):
        cls = tool_types[tool_type]
        tlist = sorted(tool_classes[tool_type].keys())
        helptext = "%s (%s)" % (cls._short_help, ", ".join(tlist))
        res.append(("-%s" % cls._short_opt, "--%s" % cls._type, helptext))
    return res

def debug_tools():
    for name, cls in tool_types.iteritems():
        log.debug("Tool-Type '%s'; short option: %s; merge: %s"
            % (cls._type, cls._short_opt, cls._merge_classes))
        for tname, cls in tool_classes[name].iteritems():
            log.debug(" %s '%s'" % (cls._type, cls._name))
            log.debug("   using global arguments: %s" % str(cls.global_args()))
            log.debug("   local arguments: %s" % str(cls.args()))

class ToolCreator(type):
    def __new__(cls, name, baseClasses, classdict):
        ncls = type.__new__(cls, name, baseClasses, classdict)
        if hasattr(ncls, "_type"):
            if hasattr(ncls, "_name"):
                tool_classes.setdefault(ncls._type, {})[ncls._name] = ncls
            else:
                tool_classes.setdefault(ncls._type, {})
                tool_types[ncls._type] = ncls
        elif not "__metaclass__" in classdict: 
            # only "Tool" is allowed to have no _type
            print "WARNING: Found Tool without type: %s" % name
        return ncls

class Tool(object):
    __metaclass__ = ToolCreator

    """Name of this tool"""
    #_name = "Empty"

    """list of Arguments to this tool (Arg class)"""
    _args = ()

    """list of (string) global arguments which are used - they are copied into options"""
    _global_args = ()

    """Set to true for example in Layout; if the classes should be merged
    and one tool created instead of instantiating every class.
    You need one FundamentalTool in the list!"""
    _merge_classes = False

    @classmethod
    def args(cls):
        args_names = []
        args_list = []
        for base_class in reversed(cls.mro()):
            if hasattr(base_class, "_args"):
                for arg in base_class._args:
                    if not arg.name in args_names:
                        args_names.append(arg.name)
                        args_list.append(arg)
        return zip(args_names, args_list)

    @classmethod
    def decorate(cls, name, title=None):
        if title is None:
            title = name
        def decorated(func):
            return classobj(name, (cls,), dict(_name=title, __call__=func))
        return decorated

    @classmethod
    def global_args(cls):
        args = set()
        for base_class in cls.mro():
            if hasattr(base_class, "_global_args"):
                args.update(base_class._global_args)
        return args

    @classmethod
    def tools_from_options(cls, options):
        res = {}
        for tool_type in sorted(tool_types.keys()):
            tool_strings = getattr(options, tool_type.replace("-","_"))
            tools = cls.tools_from_strings(tool_type, tool_strings, options)
            res[tool_type] = tools
        return res

    @classmethod
    def tools_from_strings(cls, tool_type, tool_strings, options):
        type_cls = tool_types[tool_type]
        tools = []
        # Regex: Require ":" but without an (unescaped) backslash
        ts_split = [re.split(r"(?<!\\)\:", s) for s in tool_strings]
        class_args = []
        for n in ts_split:
            tool_name, args = n[0], n[1:]
            if not tool_name in tool_classes[tool_type]:
                choices = ", ".join(tool_classes[tool_type].keys())
                raise ArgParseError("no such %s: %s\npossible choices are: %s" % 
                    (tool_type, tool_name, choices))
            class_args.append((tool_classes[tool_type][tool_name], args))
            
        classes = [c for c, a in class_args]
        if type_cls._merge_classes:
            specific_class = cls.create_specific_class(tool_type, classes)
            tool = specific_class()
            tool.read_global_options(options)
            for bcls, args in class_args:
                tool.read_options(args)
            tools = [tool]
        else:
            tools = []
            for tool_class, args in class_args:
                tool = tool_class()
                tool.read_global_options(options)
                tool.read_options(args)
                tools.append(tool)
        return tools

    @classmethod
    def create_specific_class(cls, tool_type, classes):
        """
        Compose a new layout from other layouts. This is tricky because we 
        dynamically create a new layout class out of objects passed on the 
        commandline. This means that the commandline must follow Python's 
        inheritance rules. Not ideal, but convenient for the moment.
        """
        bases = tuple(reversed(classes))
        n_fundamental = len([1 for b in bases if issubclass(b, FundamentalTool)])
        if n_fundamental != 1:
            # We didn't include a fundamental layout or have more than one!
            blist= ", ".join(tc._name for tc in tool_classes[tool_type].values()
                             if issubclass(tc, FundamentalTool))
            if n_fundamental == 0:
                msg = ("You tried to construct a combination of {type}s "
                       "without including one of the base {type}s. Please "
                       "use at least one of the following {type}s: {blist}"
                       "".format(type=tool_type, blist=blist))
            else:
                msg = ("You tried to construct a combination of {type}s "
                       "with more than one base {type}s. "
                       "Please use only one of these {type}s: "
                       "{blist}".format(type=tool_type, blist=blist))

            raise ArgParseError(msg)
        
        return classobj("%s_specific" % tool_type, bases, {})

    def read_global_options(self, global_args):

        # Primary default for all options is None
        args = self.args()
        self.options = dict(((name, arg.default) for name, arg in args))

        # Use any global args that are specified
        for arg in self.global_args():
            if not hasattr(global_args, arg):
                raise ToolParseError(self, "unknown global argument '%s'" % arg)
            self.options[arg] = getattr(global_args, arg)

        log.debug("%s %s options after global args: %s" % (self._type, self._name, self.options))

    def read_options(self, args):
        my_args = self.args()
        my_args_dict = dict(my_args)

        keyword_args = {}
        positional_args = {}

        # Now update with local options
        for arg in args:
            # Try to find an unescaped equal sign
            tp = re.split(r"(?<!\\)\=", arg)
            if len(tp) == 2:
                arg, val = tp
                if not arg in my_args_dict:
                    raise ToolParseError(self, "unknown argument '%s'" % arg)
                try:
                    cval = my_args_dict[arg].converter(val)
                except Exception, x:
                    raise ToolParseError(self, "cannot convert '%s'" % val)
                keyword_args[arg] = cval
            elif len(tp) == 1:
                positional_args.append(arg)
            else:
                raise ToolParseError(self, "too many '=' in %s" % arg)

        if len(positional_args) > len(my_args):
            raise ToolParseError(self, "too many arguments!")

        positional_args = dict(zip((n for n, arg in my_args), positional_args))
        for arg in keyword_args:
            if arg in positional_args:
                raise ToolParseError(self, "argument '%s' specified as both "
                                     "positional and keyword argument" % arg)

        self.options.update(keyword_args)
        self.options.update(positional_args)

        for arg, val in self.options.iteritems():
            if arg in my_args_dict and my_args_dict[arg].choices:
                if not val in my_args_dict[arg].choices:
                    raise ToolParseError(self, "invalid choice '%s' (%s)" 
                                % (val, ", ".join(my_args_dict[arg].choices)))

        log.debug("%s %s options after local args: %s" % (self._type, self._name, self.options))

class FundamentalTool(object):
    """
    Needed for tool types which merge classes. 
    At least one class must have this.
    """
