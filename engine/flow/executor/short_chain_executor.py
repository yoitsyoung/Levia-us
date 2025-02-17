from engine.llm_provider.llm import chat_completion
from memory.episodic_memory.episodic_memory import retrieve_short_pass_memory
from engine.flow.executor.tool_executor import execute_tool
from engine.flow.planner.planner import create_execution_plan
from engine.utils.json_util import extract_json_from_str
import json

from engine.tool_framework.tool_caller import ToolCaller
from engine.flow.executor.tool_executor import verify_tool_execution
from engine.flow.tool_selector.tool_select import tool_select
from engine.flow.tool_selector.step_necessity_validator import step_tool_check
from engine.flow.executor.next_step_prompt import next_step_prompt
import os
from memory.short_term_memory.short_term_memory import ShortTermMemory
from engine.utils.chat_formatter import create_chat_message
from engine.tool_framework.tool_caller import ToolCaller
from engine.tool_framework.tool_registry import ToolRegistry
from memory.plan_memory.plan_memory import PlanContextMemory
from metacognitive.stream.stream import output_stream
from engine.flow.planner.tool_base_planner import tool_base_planner

registry = ToolRegistry()
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
print(f"registry project_root: {project_root}")
tools_dir = os.path.join(project_root, "tools")
registry.scan_directory(tools_dir)
tool_caller_client = ToolCaller(registry)

plan_context_memory = PlanContextMemory()
short_term_memory = ShortTermMemory()
QUALITY_MODEL_NAME = os.getenv("QUALITY_MODEL_NAME")
CHAT_MODEL_NAME = os.getenv("CHAT_MODEL_NAME")
INTERACTION_MODE = os.environ.get("INTERACTION_MODE", "terminal")

def execute_intent_chain(
    user_intent: str,
    messages_history: list,
    user_id: str
):   
    output_stream(f" - Do not have experience for {user_intent} - \n")
    print(f"\033[93m - Creating new execution plan ... - \033[0m\n")
    plan = create_execution_plan(user_intent)
    process_tool_execution_plan(
        plan, messages_history, user_id, user_intent
    )
    return plan

def process_tool_execution_plan(plan, messages_history: list, user_id: str, user_intent: str):
    """
    Handle execution of new tools based on the plan
    
    Args:
        execution_records_str: List to store execution records
        summary: Summary of the execution plan
        plan: Plan containing steps to execute
        messages_history: History of conversation messages
        
    Returns:
        list: Records of tool execution results
    """
    # Analyze each step and find appropriate tools
    found_tools = []
    for step_index, step in enumerate(plan):
        print(f"\033[93m - finding appropriate tool for step: {step['intent']} - \033[0m\n")
        found_tools.extend(resolve_tool_for_step(step))

    #replan
    found_tools = get_unique_tools(found_tools)
    plan = tool_base_planner(user_intent, found_tools)
    print(f" - replan: {plan} - \n")
            
    if(plan["status"] == "failed"):
        return plan
    plan = plan["plan"]

    # Execute tools for each plan step
    process_plan_execution(messages_history, plan, user_id)
    
    all_steps_executed = all(step.get("executed", False) for step in plan)
    if all_steps_executed:
        plan_context_memory.create_plan_context(plan, user_id)

def get_unique_tools(found_tools):
    unique_tools = []
    tool_ids = set()
    for tool in found_tools:
        tool_id = tool['id']
        if tool_id and tool_id not in tool_ids:
            tool_ids.add(tool_id)
            unique_tools.append(tool)
    return unique_tools

def process_plan_execution(messages_history, plan_steps, user_id: str):
    # tool_results = []
    for step_index, step in enumerate(plan_steps):
        # if not step.get("tool_necessity", True):
        #     continue
        if step.get("executed", False):
            continue
            
        tool_result = execute_step_tool(
            messages_history,
            step,
            plan_steps,
            user_id,
            step_index
        )
        step["tool_executed_result"] = tool_result["result"]
        if tool_result["status"] == "failure":
            step["executed"] = True
            break
        elif tool_result["status"] == "need_input":
            step["executed"] = False
            break
        else:
            step["executed"] = True
    # return tool_results
    
def validate_step_necessity(step, plan, messages_history, done_steps):
    """Check if a step is necessary to execute"""
    result = step_tool_check(plan, step, messages_history, done_steps)
    return extract_json_from_str(result)

def resolve_tool_for_step(step):
    """Find appropriate tool for a step from memory"""
    memories = retrieve_short_pass_memory(step["description"])
    if not memories:
        return False
    return memories["matches"]

def execute_step_tool(messages_history,step, plan_steps, user_id: str, step_index: int):
    """
    Execute tool for a plan step
    
    Returns:
        str: Tool execution record if successful, None otherwise
    """
    tool_config = parse_tool_config(step)
    
    def execute_with_config(messages_history):
        reply_json = validate_tool_parameters(
            tool_config,
            messages_history, 
            plan_steps,
            step
        )
        
        if not reply_json["can_proceed"]:
            return {
                "toolName": step["tool"],
                "result": f"Please input required arguments to continue: {reply_json['missing_required_arguments']}", 
                "status": "need_input"
            }
            
        execution_result = execute_tool_operation(tool_config, reply_json)
        if execution_result == {"status": "failure"}:
            return {
                "toolName": step["tool"],
                "result": "execution failed",
                "status": "failure"
            }
            
        if execution_result:
            plan_context_memory.update_step_status_context(
                step_index,
                execution_result=execution_result,
                executed=True,
                user_key=user_id
            )
            method_metadata = extract_json_from_str(step['data'])
            # print(f" - method_metadata: {method_metadata} - \n")
            if method_metadata['inputs']:
                for input in method_metadata['inputs']:
                    if isinstance(input, dict):
                        append_input_param = reply_json['extracted_arguments']['required_arguments'][input['name']]
                        del append_input_param['value']
                        input.update(append_input_param)
                step['data'] = method_metadata
            return {
                "toolName": step["tool"],
                "result": execution_result,
                "status": "success"
            }
        return None
    
    return execute_with_config(messages_history)

def parse_tool_config(tool):
    tool_dict = extract_json_from_str(tool["data"])
    tool_name =tool["tool"]
    tool_dict["tool"] = tool_name
    return tool_dict

def validate_tool_parameters(tool_config, messages_history, plan_steps, step):
    """Attempt to execute tool with current configuration"""
    next_step_content = next_step_prompt(plan_steps, tool_config, messages_history)
    prompt = [{"role": "user", "content": next_step_content}]
    
    reply = chat_completion(prompt, model=QUALITY_MODEL_NAME, config={"temperature": 0})
    reply_json = extract_json_from_str(reply)
    output_stream(f" - {reply_json} - \n")
    return reply_json

def execute_tool_operation(tool_config, reply_json):
    """Execute tool with provided arguments"""
    args = {}
    required_args = reply_json.get("extracted_arguments", {}).get("required_arguments", {})
    for arg_name, arg_info in required_args.items():
        args[arg_name] = arg_info.get("value", {})

    result,_ = execute_tool(
        tool_caller_client,
        tool_config['tool'],
        tool_config['method'],
        args
    )
    
    if verify_tool_execution(tool_config, result) == "success":
        return result
    return {"status": "failure"}

def handle_user_input(user_id: str):
    """Handle failed tool execution by requesting user input"""
    user_input = input("Please input required arguments to continue: ")
    if not user_input:
        return False
    short_term_memory.add_context(create_chat_message("user", user_input), user_id)
    return True
