from logging import getLogger

from mcviz import Tool, FatalError
from mcviz.graph import GraphView
from mcviz.tools import ToolSetting, ArgParseError, debug_tools
from mcviz.tools.transforms.tagging import tag
from mcviz.utils import timer


class GraphWorkspace(object):

    def __init__(self, name, event_graph):
        self.name = name
        self.log = getLogger(name)
        self.log.debug('Creating new graph workspace')
        self.event_graph = event_graph
        self.log.debug('Creating graph view')
        self.graph_view = GraphView(event_graph)
        self.layout = None
        self.tools = {}

    def load_tools(self, options):
        debug_tools()
        self.log.debug('Loading tools...')
        with timer('load all tools'):
            try:
                settings = ToolSetting.settings_from_options(options)
                self.tools_from_settings(settings)
            except ArgParseError, e:
                self.log.fatal("Parse error in arguments: %s" % e.args[0])
                raise FatalError

    def tools_from_settings(self, settings):
        optionsets = settings.pop("optionset")
        for optionset in Tool.build_tools("optionset", optionsets):
            optionset(settings)
        for tool_type in settings:
            tools = Tool.build_tools(tool_type, settings[tool_type])
            self.tools[tool_type] = tools
    
    def apply_tools(self, tool_type, *args):
        tools = self.tools.get(tool_type, ())
        for tool in tools:
            self.log.verbose('applying %s: %s' % (tool_type, tool))
            with timer('apply %s' % tool):
                tool(*args)

    def apply_tags(self):
        # Apply all Taggers on the graph
        self.log.debug('tagging graph')
        with timer('tag the graph'):
            tag(self.graph_view)

    def clear_tags(self):
        self.log.debug('TODO: remove tags from graph')
    
    def apply_transforms(self):
        self.log.debug("Graph state (before transforms): %s", self.graph_view)
        self.log.verbose("applying transforms")
        with timer("apply all transforms", self.log.VERBOSE):
            self.apply_tools("transform", self.graph_view)
        self.log.debug("Graph state (after transforms): %s", self.graph_view)

    def clear_transforms(self):
        self.log.debug('Recreating graph view')
        self.graph_view = GraphView(self.event_graph)

    def apply_annotations(self):
        # Apply any specified annotations onto the layouted graph
        self.log.verbose("applying annotations")
        with timer("applied all annotations"):
            self.apply_tools("annotation", self.graph_view)

    def clear_annotations(self):
        self.log.debug('TODO: remove annotations from graph')

    def create_layout(self):
        # Get the specified layout class and create a layout of the graph
        self.log.verbose("applying layout classes")
        with timer("layout the graph", self.log.VERBOSE):
            layout, = self.tools["layout"]
            self.layout = layout(self.graph_view)

    def run_layout_engine(self):
        self.log.verbose("running layout engine")
        with timer("run layout engine", self.log.VERBOSE):
            self.apply_tools("layout-engine", self.layout)

    def apply_styles(self):
        # Apply any specified styles onto the layouted graph
        self.log.verbose("applying styles")
        with timer("applied all styles"):
            self.apply_tools("style", self.layout)

    def clear_styles(self):
        self.log.debug('TODO: remove styles from graph')

    def apply_optionsets(self):
        # Apply any specified styles onto the layouted graph
        self.log.verbose("applying optionsets")
        with timer("applied all optionsets"):
            self.apply_tools("optionset", self.tools)

    def paint(self):
        self.log.verbose("painting the graph")
        with timer("painted the graph"):
            self.apply_tools("painter", self.layout)
       
    def restyle(self):
        self.clear_tags()
        self.clear_styles()
        self.clear_annotations()
        self.apply_tags()
        self.apply_annotations()
        self.apply_styles()

    def run(self):
        self.apply_optionsets()
        self.apply_transforms()
        self.apply_tags()
        self.apply_annotations()
        self.create_layout()
        self.apply_styles()
        self.run_layout_engine()
        self.paint()