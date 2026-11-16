from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

class Defenses(StrictModel):
    separate_instructions: bool = True
    least_privilege: bool = True
    validate_schema_and_budget: bool = True
    require_approval: bool = True

class TextInput(StrictModel):
    text: str = Field(min_length=1, max_length=12000)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.text.strip():
            raise ValueError("text cannot be blank")
        return self

class SimulationInput(StrictModel):
    scenario_id: Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"] | None = None
    task: str | None = Field(default=None, min_length=1, max_length=1000)
    source: str | None = Field(default=None, min_length=1, max_length=12000)
    defenses: Defenses = Field(default_factory=Defenses)

    @model_validator(mode="after")
    def choose_input(self):
        if self.scenario_id:
            if self.task is not None or self.source is not None:
                raise ValueError("Provide scenario_id OR task + source, not both")
        elif self.task is None or self.source is None:
            raise ValueError("Provide scenario_id OR both task and source")
        if self.task is not None and not self.task.strip():
            raise ValueError("task cannot be blank")
        if self.source is not None and not self.source.strip():
            raise ValueError("source cannot be blank")
        return self

class ActionProposal(StrictModel):
    # This is data for the policy engine, NOT an executable function call.
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)

class PolicyInput(StrictModel):
    proposal: ActionProposal
    defenses: Defenses = Field(default_factory=Defenses)

class SuiteInput(StrictModel):
    defenses: Defenses = Field(default_factory=Defenses)
