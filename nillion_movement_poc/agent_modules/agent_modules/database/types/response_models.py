# Third-party imports
from typing import List, Union
from pydantic import BaseModel, Field


class RequirementCheckerResponse(BaseModel):
    """The response of the requirement checker"""

    message: str = Field(
        description=(
            "The primary content of the response. This can either be: "
            "1. A question directed to the user, clearly indicating what additional information or confirmation is needed (with the is_final_response=False). "
            "2. The fulfilled action without any additional text (with the is_final_response=True)"
        )
    )
    is_final_response: bool = Field(
        default=False,
        description=(
            "A boolean field that indicates whether the response is final and the input is complete, confirmed, and ready to proceed to the next step. "
            "Set to True only if no further clarification, confirmation, or input is required from the user. "
            "If the user needs to provide additional information or take further action, it should remain False."
        )
    )
    is_cancelled: bool = Field(
        default=False,
        description="A boolean field that indicates whether the user has cancelled the action."
    )
    
class EstimationParam(BaseModel):
    """Represents a parameter for estimation."""
    param: str = Field(description="The name of the parameter.")
    value: Union[float, str] = Field(description="The value of the parameter corresponding to its name.")

class EstimationStep(BaseModel):
    """Represents a step in the estimation process."""
    method: str = Field(description="The name of the method.")
    params: List[EstimationParam] = Field(default=[], description="A list of parameters for the method.")

class GasEstimatorResponse(BaseModel):
    """Represents the response of the requirement checker."""
    estimation_steps: List[EstimationStep] = Field(default=[], description="A list of estimation steps, where each element includes the method's name and its associated parameter-value pairs.")

class EvaluatorResponse(BaseModel):
    """The response of the message evaluator"""
    message_category: str = Field(description="[Message Category] (e.g., FINANCIAL, INFORMATIONAL, or PRIVATE_DATA")
    message_subcategory: str = Field(description="[Message Subcategory] base on the message category, for example: FINANCIAL category has subcategories such as TRADE and TRANSFER.")
    confidence: float = Field(description="A number between 0.00 and 1.00 representing your confidence level in the classification")

class PlannerResponse(BaseModel):
    """The response of the planner"""
    plan: List[str] = Field(default=[], description="A list of actions to be executed. Return an empty list if no action is needed.")
    error_message: str = Field(default="", description="An error message if the plan is not valid. Return an empty string if no error is found.")

class SubPromptsBreakerResponse(BaseModel):
    """The response of the sub-prompts breaker"""
    sub_prompts: List[str] = Field(default=[], description="A list of sub-prompts.")
