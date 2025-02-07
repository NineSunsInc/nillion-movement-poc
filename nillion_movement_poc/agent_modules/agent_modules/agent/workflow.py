from typing import Literal
from langgraph.graph import StateGraph, START
from langgraph.pregel import RetryPolicy
from agent_modules.database.types.state import PlanExecute, Category, Subcategory

class AgentWorkflow:
    """Handles the workflow configuration and graph compilation"""
    
    def __init__(self, agent_instance):
        self.agent = agent_instance
        
    def compile_graph(self, user_store, memory):
        workflow = StateGraph(PlanExecute)
        
        self._add_nodes(workflow)
        self._add_edges(workflow)
        
        return workflow.compile(
            checkpointer=memory,
            store=user_store,
            interrupt_before=["ask_user", "confirm_gas"]
        )
    
    def _add_nodes(self, workflow):
        """Add all nodes to the workflow"""
        nodes = {
            # "classifier": self.agent.classifier.get_step(),
            "safety_classifier": self.agent.safety_classifier.get_step(),
            "domain_classifier": self.agent.domain_classifier.get_step(),
            "read_cacher": self.agent.read_cacher.get_step(),
            "web3_info_retriever": self.agent.web3_info_retriever.get_step(),
            "user_data_retriever": self.agent.user_data_retriever.get_step(),
            "requirement_checker": self.agent.requirement_checker.get_step(),
            "ask_user": self._ask_human,
            "planner": self.agent.planner.get_step(),
            "information_retriever": self.agent.information_retriever.get_step(),
            "blockchain_executor": self.agent.blockchain_executor.get_step(),
            "task_supervisor": self.agent.task_supervisor.get_step(),
            "gas_estimator": self.agent.gas_estimator.get_step(),
            "confirm_gas": self._confirm_gas,
            "dynamic_formatter": self.agent.dynamic_formatter.get_step(),
            "sub_prompts_checker": self.agent.sub_prompts_checker.get_step(),
            "sub_prompts_breaker": self.agent.sub_prompts_breaker.get_step()
        }
        
        for name, node in nodes.items():
            if name in ["information_retriever", "blockchain_executor"]:
                workflow.add_node(name, node, retry=RetryPolicy(max_attempts=1))
            else:
                workflow.add_node(name, node)
    
    def _add_edges(self, workflow):
        """Configure the workflow edges and conditions"""
        # Add basic edges
        workflow.add_edge("information_retriever", "task_supervisor")
        workflow.add_edge("blockchain_executor", "task_supervisor")
        workflow.add_edge(START, "safety_classifier")
        workflow.add_edge("sub_prompts_breaker", "sub_prompts_checker")
        workflow.add_edge("domain_classifier", "read_cacher")
        workflow.add_edge("ask_user", "requirement_checker")
        workflow.add_edge("gas_estimator", "confirm_gas")
        workflow.add_edge("confirm_gas", "planner")
        workflow.add_edge("web3_info_retriever", "dynamic_formatter")
        workflow.add_edge("user_data_retriever", "dynamic_formatter")

        # Add conditional edges
        workflow.add_conditional_edges("requirement_checker", self._should_ask_human)
        workflow.add_conditional_edges("planner", self._able_to_plan)
        workflow.add_conditional_edges("task_supervisor", self._task_distributing)
        workflow.add_conditional_edges("read_cacher", self._verify_cached_data)
        workflow.add_conditional_edges("sub_prompts_checker", self._sub_prompts_check)
        workflow.add_conditional_edges("dynamic_formatter", self._check_is_final_response)
        workflow.add_conditional_edges("safety_classifier", self._is_rejected)

    @staticmethod
    def _ask_human(state: PlanExecute):
        """Fake node for asking human"""
        pass

    @staticmethod
    def _confirm_gas(state: PlanExecute):
        """Fake node for confirming gas cost"""
        pass
    
    @staticmethod
    def _should_ask_human(state: PlanExecute) -> Literal["gas_estimator", "ask_user", "__end__"]:
        if state.get('is_cancelled'):
            return "__end__"
        return "ask_user" if state['ask_human_question'] else "gas_estimator"
    
    @staticmethod
    def _check_is_final_response(state: PlanExecute) -> Literal["__end__", "sub_prompts_checker"]:
        if state['category'] == Category.FINAL_RESPONSE:
            return "__end__"
        return "sub_prompts_checker"

    @staticmethod
    def _sub_prompts_check(state: PlanExecute) -> Literal["domain_classifier", "dynamic_formatter"]:
        if state['input'] == "":
            return "dynamic_formatter"
        return "domain_classifier"

    @staticmethod
    def _able_to_plan(state: PlanExecute) -> Literal["task_supervisor", "dynamic_formatter"]:
        return "task_supervisor" if state['plan'] else "dynamic_formatter"
    
    @staticmethod
    def _task_distributing(state: PlanExecute) -> Literal["information_retriever", "blockchain_executor", "dynamic_formatter"]:
        if state.get('error_message'):
            return "dynamic_formatter"
        return state['next_executor_node']
    
    @staticmethod
    def _verify_cached_data(state: PlanExecute) -> Literal["requirement_checker", "dynamic_formatter", "user_data_retriever", "web3_info_retriever"]:
        category = state.get("category", None)    

        if category == Category.BLOCKCHAIN_ACTION:
            return "requirement_checker"
        elif category == Category.PRIVATE_DATA:
            return "user_data_retriever"
        elif category == Category.WEB3_INFORMATION:
            return "web3_info_retriever"
        # [Category.REJECTED, Category.NEEDS_CLARIFICATION] and None
        else:
            return "dynamic_formatter"
    
    @staticmethod
    def _is_rejected(state: PlanExecute) -> Literal["sub_prompts_breaker", "dynamic_formatter"]:
        if state.get('category', None) == Category.REJECTED:
            return "dynamic_formatter"
        return "sub_prompts_breaker"
