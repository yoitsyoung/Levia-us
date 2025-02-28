import sys
import os

# Get absolute path of current file
current_file_path = os.path.abspath(__file__)

# Get project root path (3 levels up)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file_path))))

# Add project root to Python path
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from engine.llm_provider.llm import chat_completion
from engine.utils.json_util import extract_json_from_str
from engine.flow.chat_handler_flow.intents_system_prompt import intents_system_prompt

def get_initial_response(chat_messages: list) -> dict:
    """Get initial response from LLM"""
    prompt = intents_system_prompt(chat_messages)
    reply_info = chat_completion(prompt, model="deepseek-chat", config={"temperature": 0})
    return extract_json_from_str(reply_info)


def main():
    # chat_messages = input("Enter your message: ")
    chat_messages = [{"role": "user", "content": "tell me the newest football news"},
                     {"role": "assistant", "content": "2027-02-09, Chinese football team won the world cup"},
                     {"role": "user", "content": "who are you?"},
                     {"role": "assistant", "content": 'I am Levia, an AI within a Living Agent Ecosystem, designed for understanding and action. I can integrate tools, process real-world information, and improve through interaction.'},
                     {"role": "user", "content": "What did you said with the news? Sounds impossible."}
                     ]
    result = get_initial_response(chat_messages=chat_messages)

    print(result)




if __name__ == "__main__":
    main()
