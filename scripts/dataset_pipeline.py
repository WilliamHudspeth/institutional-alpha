import json
import os
from typing import Any

from langchain.agents.agent_types import AgentType
from langchain.prompts import PromptTemplate
from langchain_community.chat_models import ChatOllama
from langchain_experimental.agents.agent_toolkits import create_csv_agent

# ==========================================
# 1. LLM Initialization (ChatOllama)
# ==========================================
# Initializing LLaMA3 7B for complex reasoning and 4B for simple retrieval
llm_7b = ChatOllama(model="llama3-7b", temperature=0)
llm_4b = ChatOllama(model="llama3-4b", temperature=0)

# ==========================================
# 2. Prompt Templates (Aswath Damodaran FCFF)
# ==========================================
# Damodaran's Free Cash Flow to the Firm (FCFF) Equation
fcff_template = """
You are an expert financial analyst following Aswath Damodaran's valuation principles.
Calculate the Free Cash Flow to the Firm (FCFF) based on the provided inputs.

Formula:
FCFF = EBIT * (1 - Tax Rate) + Depreciation & Amortization - Capital Expenditures - Change in Non-Cash Working Capital

Inputs:
EBIT: {ebit}
Tax Rate: {tax_rate}
Depreciation & Amortization: {depreciation}
Capital Expenditures (CapEx): {capex}
Change in Non-Cash Working Capital: {change_in_nwc}

Instructions:
1. Show your step-by-step calculation.
2. Return the final FCFF value in a valid JSON format: {{"FCFF": <value>}}.
"""

fcff_prompt = PromptTemplate(
    input_variables=["ebit", "tax_rate", "depreciation", "capex", "change_in_nwc"],
    template=fcff_template,
)


# ==========================================
# 3. JSON Validation Utility
# ==========================================
def validate_and_parse_json(output: str) -> dict[str, Any]:
    """Validates and parses JSON from the agent's output."""
    try:
        # Simple extraction in case the model wraps the JSON in markdown code blocks
        if "```json" in output:
            output = output.split("```json")[1].split("```")[0].strip()
        elif "```" in output:
            output = output.split("```")[1].split("```")[0].strip()

        parsed_data = json.loads(output)
        return parsed_data
    except json.JSONDecodeError as e:
        print(f"JSON Validation Error: {e}")
        return {"error": "Invalid JSON format", "raw_output": output}


# ==========================================
# 4. Routing Logic & Agent Executor Setup
# ==========================================
def route_and_execute_task(task_type: str, query: str, csv_path: str) -> str:
    """
    Routes the task based on complexity.
    - 'simple_retrieval': Routes to 4B model.
    - 'complex_reasoning': Routes to 7B model.
    """
    if task_type == "simple_retrieval":
        print("[Router] Routing task to LLaMA3-4B (Simple Retrieval)...")
        selected_llm = llm_4b
    elif task_type == "complex_reasoning":
        print("[Router] Routing task to LLaMA3-7B (Complex Reasoning)...")
        selected_llm = llm_7b
    else:
        raise ValueError("Unknown task_type. Must be 'simple_retrieval' or 'complex_reasoning'.")

    # Implementing handle_parsing_errors=True in the agent executor
    agent = create_csv_agent(
        selected_llm,
        csv_path,
        verbose=True,
        agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        handle_parsing_errors=True,  # Crucial for handling output parsing errors
    )

    try:
        response = agent.run(query)
        return response
    except Exception as e:
        return f"Agent Execution Error: {str(e)}"


# ==========================================
# 5. Example Execution
# ==========================================
if __name__ == "__main__":
    # Create a dummy dataset for the prototype
    sample_csv = "financial_dataset.csv"
    with open(sample_csv, "w") as f:
        f.write("Company,Year,EBIT,Tax_Rate,Depreciation,CapEx,Change_in_NWC\n")
        f.write("AAPL,2023,100000,0.21,10000,15000,5000\n")
        f.write("MSFT,2023,80000,0.21,8000,12000,4000\n")

    print("=== Pipeline Prototype ===")

    # Task 1: Simple Retrieval (4B)
    print("\n--- Task: Simple Retrieval ---")
    retrieval_query = "What is the CapEx for AAPL in 2023?"
    retrieval_result = route_and_execute_task("simple_retrieval", retrieval_query, sample_csv)
    print(f"Result: {retrieval_result}")

    # Task 2: Complex Reasoning (7B)
    print("\n--- Task: Complex Reasoning (FCFF Calculation) ---")

    # We can use the prompt template to format our query
    complex_query = fcff_prompt.format(
        ebit="100000", tax_rate="0.21", depreciation="10000", capex="15000", change_in_nwc="5000"
    )

    reasoning_result = route_and_execute_task("complex_reasoning", complex_query, sample_csv)
    print(f"Raw Result: {reasoning_result}")

    # Task 3: JSON Validation
    print("\n--- Task: JSON Validation ---")
    validated_json = validate_and_parse_json(reasoning_result)
    print(f"Parsed Output: {validated_json}")

    # Clean up
    if os.path.exists(sample_csv):
        os.remove(sample_csv)
