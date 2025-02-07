from agent_modules.agent.workflow import AgentWorkflow

class Agent:
    """Main agent class that coordinates all components"""
    
    def __init__(self, **nodes):
        self._initialize_nodes(nodes)
        self.workflow = AgentWorkflow(self)
    
    def _initialize_nodes(self, nodes):
        """Initialize all node attributes from the provided nodes dictionary"""
        for name, node in nodes.items():
            setattr(self, name, node)
    
    def compile_graph(self, user_store, memory):
        """Compile the agent workflow"""
        return self.workflow.compile_graph(user_store, memory)