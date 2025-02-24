# Standard library imports
import asyncio
import csv
import uuid
import json
import chainlit as cl

# Third-party imports
from abc import ABC, abstractmethod
from langchain_core.language_models import BaseChatModel
from langgraph.store.base import BaseStore
from agent_modules.classifier.blockchain_action.ft_blockchain_actions_classifier import BlockchainActionClassifier
from agent_modules.classifier.domain.ft_domain_action_classifier_v3 import DomainClassifierV3
from agent_modules.database.types.safety_result import SafetyResult
from sentence_transformers import CrossEncoder
from langchain_core.outputs import LLMResult
from datetime import datetime
from typing import Any, List, cast

# Local application imports
from agent_modules.database.const.prompt import *
from agent_modules.database.repositories.embedding_repository import EmbeddingRepository
from agent_modules.database.repositories.opensearch_repository import (
    OpenSearchRepository, 
    SearchType, 
    SearchResult
)
from agent_modules.database.repositories.response_record_repository import ResponseRecordRepository
from agent_modules.database.types.document import Document
from agent_modules.database.types.response_models import (
    EvaluatorResponse,
    PlannerResponse,
    RequirementCheckerResponse,
    GasEstimatorResponse,
    EstimationStep,
    SubPromptsBreakerResponse
)
from agent_modules.database.types.state import PlanExecute, Category, Subcategory
from agent_modules.database.types.search_result import SerperSearchResult
from agent_modules.agent.resources.agent_config import DEBUG, AgentConfig
from agent_modules.agent.strategies.format_strategies import (
    FormatStrategy,
    ConcreteFormatStrategyAction,
    ConcreteFormatterStrategyReject,
    ConcreteFormatStrategyClarify,
    ConcreteFormatStrategyUserData,
    ConcreteFormatStrategyWeb3Info,
    ConcreteFormatStrategyFinalResponse
)
from agent_modules.agent.tools import (
    estimate_total_gas_cost_swap, 
    estimate_total_gas_cost_transfer, 
    search_with_perser
)
from agent_modules.classifier.run_unified_tests_v3 import UnifiedMainClassifierV3

class BaseStep(ABC):
    @abstractmethod
    def execute(self, state: PlanExecute, store: BaseStore, *args: Any, **kwargs: Any):
        pass

class BaseRagStep(ABC):
    def _process_json_data(self, text: str):
        return text.replace("{", "{{").replace("}", "}}")
    
    def _format_retrieve_data(self, docs: List[Document]):
        return "\n".join(filter(None, [doc.text for doc in docs]))

    def _filter_retrieved_data(self, docs: tuple, distance_threshhold: float = None) -> List[Document]:
        # Set the threshold for retrieving documents
        threshhold = distance_threshhold if distance_threshhold else 10 
        return filter(None, [doc[0] if doc[1] <= threshhold else None for doc in docs])

    def _process_retrieved_data(self, docs: tuple, distance_threshhold: float = None):
        filterred_docs = self._filter_retrieved_data(docs, distance_threshhold)
        formatted_data = self._format_retrieve_data(filterred_docs)

        return formatted_data

    def _process_opensearch_result(self, docs: list[SearchResult]):
        """ Process the retrieved documents from the opensearch (Mostly format the json data)"""
        if len(docs) == 0:
            return []

        # Only take the first k documents
        cut_off_docs = docs[:AgentConfig.top_k] 

        # Format the retrieved documents    
        prompt_format_free_docs = [SearchResult(id=doc.id, source=doc.source, text=self._process_json_data(doc.text), score=doc.score) for doc in cut_off_docs]
        return prompt_format_free_docs
    
    @abstractmethod
    def execute(self, state: PlanExecute, store: BaseStore, *args: Any, **kwargs: Any):
        pass

class EvaluatorStep(BaseStep):
    def execute(self, state: PlanExecute, store: BaseStore, node: BaseChatModel):
        print("\n############## MESSAGE EVALUATOR ##############")
        output = cast(EvaluatorResponse, node.invoke({"messages": [("user", state['input'])]}))

        # Debug
        if (DEBUG):
            print("Current state:", state)
            print(output.model_dump_json())

        return {
            "messages": [("user", state["input"])],
            "category": Category[output.message_category],
            # "subcategory": Subcategory[output.message_subcategory]
        }

class SafetyClassifierStep(BaseStep):
    def execute(self, state: PlanExecute, store: BaseStore, classifier):
        print("\n############## SAFETY CLASSIFIER ##############")
        current_input = state["input"]
        safety_result = classifier.classify(current_input)

        # Debug
        if (DEBUG):
            print("Current state:", state)
            print(safety_result)

        if (safety_result["status"] == "rejected"):
            return {
                "messages": [("user", current_input)],
                "category": Category.REJECTED,
                "rejected_reason": safety_result['reason']
            }

        return {
            "messages": [("user", current_input)],
            "safety_result": SafetyResult(
                status=safety_result["status"],
                safety_score=safety_result["safety_score"],
                triggered_keywords=safety_result["triggered_keywords"]
            )
        }

class DomainClassifierStep(BaseStep):
    def execute(self, state: PlanExecute, store: BaseStore, classifier: DomainClassifierV3, subclassifier: BlockchainActionClassifier):
        print("\n############## DOMAIN CLASSIFIER ##############")
        current_input = state["input"]
        safety_result = state["safety_result"]  

        domain_result = classifier.classify(current_input, safety_result.safety_score, safety_result.triggered_keywords)
        classifier_output = subclassifier.classify_with_domain_result(domain_result, current_input)

        # Add the user's message to the context history
        response = {"messages": [("user", current_input)]}

        if (classifier_output["status"] == "accepted"):
            return self._process_accepted_result(response, classifier_output)
        elif (classifier_output["status"] == "rejected"):
            return self._process_rejected_result(response, classifier_output)
        elif (classifier_output["status"] == "needs_clarification"):
            return self._process_needs_clarification_result(response, classifier_output)

    def _process_accepted_result(self, response: dict, classifier_output: dict):
        sorted_category_list = sorted(classifier_output['domain_categories']['category_scores'], key=lambda d: d['confidence'])
        category = Category[sorted_category_list[0]['category'].upper()]

        subcategory = classifier_output['domain_categories'].get("subdomain", None)

        if category == Category.PRIVATE_DATA:
            subcategory = Subcategory.MYSELF
        elif subcategory is None:
            raise Exception("Subcategory is not found")
        else:
            subcategory = Subcategory[subcategory.upper()]

        additional_response = {
            "category": category,
            "subcategory": subcategory
        }

        return {**response, **additional_response}
    
    def _process_rejected_result(self, response: dict, classifier_output: dict):
        additional_response = {
            "category": Category.REJECTED,
            "rejected_reason": classifier_output['reason']
        }
        
        return {**response, **additional_response}

    def _process_needs_clarification_result(self, response: dict, classifier_output: dict):
        additional_response = {
            "category": Category.NEEDS_CLARIFICATION,
            "ask_human_question": classifier_output['clarification_needed']
        }

        return {**response, **additional_response}
    
class RequirementCheckerStep(BaseStep):
    def execute(self, state: PlanExecute, store: BaseStore, node: BaseChatModel):
        print("\n############## REQUIREMENT CHECKER ##############")
        messages = [("user", state["input"])]
        if 'human_responses' in state and state['human_responses']:
            for question, response in state["human_responses"]:
                messages += [("assistant", question), ("user", response)]

        output = cast(RequirementCheckerResponse, node.invoke({"messages": messages}))

        if (output.is_cancelled):
            return {
                "is_cancelled": True
            }

        # If output is not a final response -> ask user
        if not output.is_final_response:
            return {
                "ask_human_question": output.message,
                "messages": [("assistant", output.message)]
            }
        
        else:
            return {
                "ask_human_question": None,
                "input": output.message # Replace the user's input
            }

class PlannerStep(BaseStep):
    def execute(self, state: PlanExecute, store: BaseStore, node: BaseChatModel):
        print("\n############## STEP PLANNING ##############")

        output = cast(PlannerResponse, node.invoke({"messages": [("user", state['input'])]}))

        # Debug
        if (DEBUG):
            print("Current state", state)
            print("Output by LLM", output)

        return {
            "messages": [("assistant", str(output.plan))],
            "plan": output.plan,
            "error_message": output.error_message if output.error_message != "" else None
        }

class TaskSupervisorStep(BaseStep):
    def execute(self, state: PlanExecute, store: BaseStore, node: BaseChatModel):
        print("\n############## TASK SUPERVISOR ##############")
        if ("error_message" in state.keys() and state['error_message'] is not None):
            return {"next_executor_node": "dynamic_formatter"}

        if (len(state['plan']) == 0):
            return {"next_executor_node": "dynamic_formatter"}
        
        try:
            # For RunnableSequence, we don't need to manage callbacks
            response = node.invoke(
                {"messages": [("user", state['plan'][0])]}
            )
            
            # Handle different response types
            if hasattr(response, 'content'):
                content = response.content
            elif isinstance(response, str):
                content = response
            else:
                # Handle unexpected response format
                print("Unexpected response format:", response)
                content = "blockchain_executor"  # Default fallback
            
            # Clean up the response - remove extra whitespace and newlines
            content = content.strip()
            
            # Extract the executor node from JSON if present
            try:
                json_data = json.loads(content)
                next_executor_node = json_data.get("executor", "blockchain_executor")
            except json.JSONDecodeError:
                # If not JSON, use the content directly
                next_executor_node = "blockchain_executor" if "blockchain" in content.lower() else "information_retriever"
            
            # Create a proper LLMResult for the callback system
            llm_result = LLMResult(generations=[[{"text": next_executor_node}]])
            
            return {
                'next_executor_node': next_executor_node,
                'llm_result': llm_result
            }

        except Exception as e:
            print(f"Error invoking model: {e}")
            return {'next_executor_node': "dynamic_formatter"}

class GasEstimatorStep(BaseStep):
    def execute(self, state: PlanExecute, store: BaseStore, node: BaseChatModel):
        print("\n############## GAS ESTIMATOR ##############")

        output = cast(
            GasEstimatorResponse, 
            node.invoke(
                {
                    "messages": [("user", state['input'])]
                }
            )
        )
        
        # Debug
        if (DEBUG):
            print("Current state:", state)
            print("Gas calculate steps:", output)
 
        total_gas = self._estimate_gas(output.estimation_steps, store)

        return {
            "total_gas": total_gas
        }
    
    def _estimate_gas(self, steps: list[EstimationStep], store: BaseStore):
        total_gas = {
            "estimated_total_gas_cost": 0,
            "currency": ""
        }
        for step in steps:
            params_map = {param.param: param.value for param in step.params}
            if (step.method == "estimate_total_gas_cost_transfer"):
                gas_response = asyncio.run(estimate_total_gas_cost_transfer(
                    decimal_amount=params_map['decimal_amount'],
                    token_type=params_map['token_type'],
                    receiver_address=params_map['receiver_address'],
                    store=store
                ))
            elif (step.method == "estimate_total_gas_cost_swap"):
                gas_response = asyncio.run(estimate_total_gas_cost_swap(
                    store=store,
                    decimal_amount=params_map['decimal_amount'],
                    src_token_type=params_map['src_token_type'],
                    des_token_type=params_map['des_token_type']
                ))
            else:
                raise Exception("Unsupported gas estimation method")

            if "error" in gas_response:
                print("Gas estimation error:", gas_response)
                # If gas estimation runs into error
                return gas_response
            
            total_gas['estimated_total_gas_cost'] += gas_response['estimated_total_gas_cost']
            total_gas['currency'] = gas_response['currency']

        return total_gas
        
class DynamicFormatterStep(BaseStep):
    def execute(self, state: PlanExecute, store: BaseStore, node: BaseChatModel):
        category = state.get("category", None)
        # subcategory = state.get("subcategory", None)
        formatter = self._get_formatter(category)

        return formatter.format(node, state, store)

    def _get_formatter(self, category: Category) -> FormatStrategy:
        if category == Category.BLOCKCHAIN_ACTION:
            return ConcreteFormatStrategyAction()
        elif category == Category.PRIVATE_DATA:
            return ConcreteFormatStrategyUserData()
        elif category == Category.WEB3_INFORMATION:
            return ConcreteFormatStrategyWeb3Info()
        elif category == Category.REJECTED:
            return ConcreteFormatterStrategyReject()
        elif category == Category.NEEDS_CLARIFICATION:
            return ConcreteFormatStrategyClarify()
        elif category == Category.FINAL_RESPONSE:
            return ConcreteFormatStrategyFinalResponse()
        
        raise Exception("Can not find the suitable formatter")

class ReadCacherStep(BaseStep):
    def __init__(self) -> None:
        self.response_record_repository = ResponseRecordRepository()

    def execute(self, state: PlanExecute, store: BaseStore):
        print("\n############## READ CACHER ##############")
        
        # TODO: This is just the skeleton for the read cacher. Can be done later
        # response_records = self.response_record_repository.find_document_by_category_and_chain(
        #     category=state["category"],
        #     chain=state["chain"]
        # )
        # if (DEBUG):
        #     print("Cache:", response_records)

        return {
            "dump_field": ""
        }

class Web3RetrieverStep(BaseRagStep):
    def _write_to_csv(self, documents: list[SearchResult], reranked_documents: list[SearchResult]):
        with open(f"compare_reranked_documents_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "w", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Original Documents", "Reranked Documents", "Reranked Document Score"])
            for doc, reranked_doc in zip(documents, reranked_documents):
                writer.writerow([doc, reranked_doc[0], reranked_doc[1]])

    def _process_serper_search_result(self, serper_search_result: List[SerperSearchResult]):
        href_title_list = []
        content = ""

        for result in serper_search_result:
            href_title_list.append(f"[{result.title}]({result.link})")
            content += f"{result.title}:\n{result.search_text}\n\n---\n"

        return ", ".join(href_title_list), content

    def _rerank_with_cross_encoder(self, user_input: str, documents: list[SearchResult], cross_encoder: CrossEncoder):
        if len(documents) == 0:
            return []

        cross_encoder_scores = cross_encoder.predict([(user_input, f"Source of document: {doc.source}\n\nContent: {doc.text}") for doc in documents])
        reranked_documents = sorted(zip(documents, cross_encoder_scores), key=lambda x: x[1], reverse=True)

        # Write the reranked documents to a csv file for checking
        # self._write_to_csv(documents, reranked_documents)

        return [doc for doc, _ in reranked_documents] # Return the documents only

    def _search_relevant_documents(self, user_input: str, opensearch_repository: OpenSearchRepository):
        is_mighty_network_related = "mighty" in user_input.lower()

        serper_search_title, serper_search_content = self._process_serper_search_result(search_with_perser(user_input))

        # Retrieve relevant documents, this will retrieve list of documents with size of top_k (defined in opensearch_service.py)
        web_search_document = SearchResult(id=uuid.uuid4(), source="Web Search\nSources: " + serper_search_title, text=serper_search_content, score=0) if not is_mighty_network_related and serper_search_content else None   

        retrieved_documents = opensearch_repository.search(
            user_input,  
            search_type=SearchType.HYBRID
        )
        if web_search_document:
            retrieved_documents = [web_search_document] + retrieved_documents
            
        return retrieved_documents

    def _proccess_input(self, input: str):
        """Add synonym for the user's input for better search results"""
        synonym_map = {
            "movement": "movement labs",
            "0g": "0g labs"
        }

        input = input.lower()
        for key, value in synonym_map.items():
            if key in input:
                input = input.replace(key, value)

        return input

    def execute(self, state: PlanExecute, store: BaseStore, opensearch_repository: OpenSearchRepository, cross_encoder: CrossEncoder):
        print("\n############## WEB3 DOCUMENT RETRIEVER ##############")

        # Process the user's input
        input = self._proccess_input(state["input"])

        # Retrieve relevant documents, this will retrieve list of documents with size of top_k (defined in opensearch_service.py)
        relevant_documents = self._search_relevant_documents(input, opensearch_repository)
        reranked_documents = self._rerank_with_cross_encoder(input, relevant_documents, cross_encoder)

        # Format and get the most relevant documents
        formatted_documents = self._process_opensearch_result(reranked_documents)

        # Debug
        if (DEBUG):
            print("Current state", state)
            for doc in formatted_documents:
                print("="*50)
                print(doc)
                print("\n\n")   

        if formatted_documents:
            return {
                "retrieved_data": formatted_documents,
            }
        else:
            # No data retrieved
            return {
                "dump_field": ""
            }

class UserDataRetrieverStep(BaseRagStep):
    def execute(self, state: PlanExecute, store: BaseStore, user_data_embedding_repository: EmbeddingRepository):
        print("\n############## CONTEXT RETRIEVER ##############")
        user_session_id = cl.user_session.get("id")
        print("#"*30)
        print("User session id:", user_session_id)
        print("#"*30)
        # Retrieve user's data for injecting to the answerer
        user_data = user_data_embedding_repository.search(
            text=state['input'], 
            user_session_id=user_session_id,
            k=1
        )
        user_data = self._process_retrieved_data(user_data, None)
        user_data = self._process_json_data(str(user_data))


        return {
            "user_data": user_data
        }

class SubPromptsCheckerStep(BaseStep):
    def execute(self, state: PlanExecute, store: BaseStore, *args: Any, **kwargs: Any):
        print("\n############## SUB PROMPTS CHECKER ##############")

        sub_prompts = state["sub_prompts"]
        tasks = state.get("tasks", [])

        if (DEBUG):
            print("Current state:", state)

        if len(sub_prompts) == 0:
            return {
                "input": "",
                "tasks": tasks,
                "category": Category.FINAL_RESPONSE
            }
        else:
            current_prompt = sub_prompts[0]
            updated_tasks = [task if task.title != current_prompt else cl.Task(title=current_prompt, status=cl.TaskStatus.RUNNING) for task in tasks]

            return {
                "input": sub_prompts[0],
                "tasks": updated_tasks,
                
                # Reset the human responses and past steps
                "human_responses": [],
                "past_steps": []
            }

class SubPromptsBreakerStep(BaseStep):
    def execute(self, state: PlanExecute, store: BaseStore, node: BaseChatModel):
        print("\n############## SUB PROMPTS BREAKER ##############")

        output = cast(SubPromptsBreakerResponse, node.invoke({"messages": [("user", state['input'])]}))

        # Debug
        if (DEBUG):
            print("Current state:", state)
            print(output.sub_prompts)

        return {
            "sub_prompts": output.sub_prompts,
            "tasks": [cl.Task(title=sub_prompt) for sub_prompt in output.sub_prompts]
        }