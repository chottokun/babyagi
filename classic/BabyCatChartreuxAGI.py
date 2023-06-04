###### This is a modified version of OG BabyCatAGI, called BabyCatChartreuxAGI (future modifications will follow the pattern "Baby<animal>AGI"). This version requires GPT-4, it's very slow, and often errors out.######
######IMPORTANT NOTE: I'm sharing this as a framework to build on top of (with lots of errors for improvement), to facilitate discussion around how to improve these. This is NOT for people who are looking for a complete solution that's ready to use. ######

import openai
import time
import requests
from bs4 import BeautifulSoup
from collections import deque
from typing import Dict, List
import re
import ast
import json
from serpapi import GoogleSearch

# API KEYS .env
import os
from dotenv import load_dotenv
load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY')

### SET VARIABLES ##############################

# OPENAI
OPENAI_TEMPERATURE=0.2
GPT_MODEL="gpt-3.5-turbo"
LANGUAGE="English" # LANGUAGE="English" # or "Japanese"
SLEEP_TIME=30 # Seeptime(sec) for retry.

# USER AGENT
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
}

# Set variables
OBJECTIVE = "Research Japanese animation company and their works."
YOUR_FIRST_TASK = "Develop a task list." #you can provide additional instructions here regarding the task list.

### UP TO HERE ##############################

# Configure OpenAI and SerpAPI client
openai.api_key = OPENAI_API_KEY
if SERPAPI_API_KEY:
  serpapi_client = GoogleSearch({"api_key": SERPAPI_API_KEY})
  websearch_var = "[web-search] "
else:
  websearch_var = ""

# Initialize task list
task_list = []

# Initialize session_summary
session_summary = f"\n*****OBJECT****\n{OBJECTIVE}\n\n"

### Task list functions ##############################
def add_task(task: Dict):
    task_list.append(task)

def get_task_by_id(task_id: int):
    for task in task_list:
        if task["id"] == task_id:
            return task
    return None

def get_completed_tasks():
    return [task for task in task_list if task["status"] == "complete"]


# Print task list and session summary
def print_tasklist():
  print("\033[95m\033[1m" + "\n*****TASK LIST*****\n" + "\033[0m")
  for t in task_list:
      dependent_task = ""
      if t['dependent_task_ids']:
          dependent_task = f"\033[31m<dependencies: {', '.join([f'#{dep_id}' for dep_id in t['dependent_task_ids']])}>\033[0m"
      status_color = "\033[32m" if t['status'] == "complete" else "\033[31m"
      print(f"\033[1m{t['id']}\033[0m: {t['task']} {status_color}[{t['status']}]\033[0m \033[93m[{t['tool']}] {dependent_task}\033[0m")

### Tool functions ##############################

def call_llm(messages,temperature=0.0, maxtokens = 1500):

    for _ in range(3):
        try:
            response = openai.ChatCompletion.create(
                model=GPT_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=maxtokens - (int(maxtokens * 0.5) * (LANGUAGE == "Japanese")),
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                timeout = 60,
            )
            break
        except Exception as e:
            print("error", e)
            time.sleep(SLEEP_TIME)

    return response

def text_completion_tool(prompt: str):
    messages = [
        {"role": "system","content": "You are a reseach export AI. Sould analyze using only the content."},
        {"role": "user", "content": prompt}
    ]
    response = call_llm(messages=messages, temperature=0.2, maxtokens=1500)
    return response.choices[0].message['content'].strip()


def query_tools(query: str):
    ask_query_prompt = (
        f"Answer a query to search Google for our task in {LANGUAGE}'. Our task: {query}'.\n"
        "Answer only a query separated by spaces. Correct spelling if need.\n"
        "Contain only better keywords. Omit words like 'research, investigate'.\n"
        f"Our Objective: {OBJECTIVE}"
    )
    messages = [
            {"role": "system","content": "You are a reseach export AI. youc can provide an effective query to search on Google."},
            {"role": "user", "content": ask_query_prompt}
    ]

    response = call_llm(messages=messages, temperature=0)

    return response.choices[0].message['content'].strip()

def web_search_tool(query: str):
    query_words = query_tools(query)
    print("\033[90m\033[3m" + f"Searching with {query_words}.\n" + "\033[0m")
    search_results = SearchByGoogle(query_words)
    print("\033[90m\033[3m" + f"Completed search. Now scraping {len(search_results)} results.\n" + "\033[0m")
    results = ""
    # Loop through the search results
    for result in search_results:
        # Extract the URL from the result
        url = result.get('href')
        # Call the web_scrape_tool function with the URL
        print("\033[90m\033[3m" + "Scraping: "+str(url)+"" + "...\033[0m")
        content = web_scrape_tool(url, task)
        print("\033[90m\033[3m" +str(content[0:100])[0:100]+"...\n" + "\033[0m")
        results += str(content)+" \n"

    return results

def SearchByGoogle(query):
    search_params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num":5 #edit this up or down for more results, though higher often results in OpenAI rate limits
    }
    results = GoogleSearch(search_params)
    search_results = results.get_dict()
    try:
      search_results = search_results["organic_results"]
    except KeyError:
      # "No organic results found"
      search_results = {}
    search_results = simplify_search_results(search_results)
    return search_results


def simplify_search_results(search_results):
    simplified_results = []
    for result in search_results:
        simplified_result = {
            "position": result.get("position"),
            "title": result.get("title"),
            "href": result.get("link"),
            "snippet": result.get("snippet")
        }
        simplified_results.append(simplified_result)
    return simplified_results


def web_scrape_tool(url: str, task:str):
    result = ""
    content = fetch_url_content(url)
    if content is None:
        return None

    text = extract_text(content)
    print("\033[90m\033[3m"+"Scrape completed. Length:" +str(len(text))+".Now extracting relevant info..."+"...\033[0m")
    info = extract_relevant_info(OBJECTIVE, text[0:5000], task)
    links = extract_links(content)

    if info!="":
        result = f"{info} \n - ref: {url}\n"

    return result

def fetch_url_content(url: str):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"Error while fetching the URL: {e}")
        return ""

def extract_links(content: str):
    soup = BeautifulSoup(content, "html.parser")
    links = [link.get('href') for link in soup.findAll('a', attrs={'href': re.compile("^https?://")})]
    return links

def extract_text(content: str):
    soup = BeautifulSoup(content, "html.parser")
    text = soup.get_text(strip=True)
    return text

def extract_relevant_info(objective, large_string, task):
    chunk_size = 3000 - (1500 * (LANGUAGE == "Japanese"))  # Default 3000
    overlap = 500 - (250 * (LANGUAGE == "Japanese"))
    notes = ""
    
    for i in range(0, len(large_string), chunk_size - overlap):
        chunk = large_string[i:i + chunk_size]
        prompt = (
            f"Given the following Text relevant to our objective and task, refine the Original Notes to better."
            f"This should be in the following markdown format:\n"
            f"## Notes\n[Notes here]\n\n"
            f"Answer the Notes in {LANGUAGE}.\n"
            f"Our objective: {objective}\n"
            f"Our task: {task}\n"
            f"Text:\n---------\n{chunk}\n---------\nOriginal Notes:\n---------\n{notes}\n---------\n"
        )
        messages = [
            {"role": "system", "content": "you are expert AI."},
            {"role": "user", "content": prompt}
        ]
        # print(notes)
        response = call_llm(messages=messages, temperature=0.7, maxtokens=800)
        note_response = response.choices[0].message['content'].strip()+"\n"
        notes = note_response
    return notes

### Agent functions ##############################
def execute_task(task, task_list, OBJECTIVE):
    global task_id_counter
    # Check if dependent_task_ids is not empty
    if task["dependent_task_ids"]:
      all_dependent_tasks_complete = True
      for dep_id in task["dependent_task_ids"]:
          dependent_task = get_task_by_id(dep_id)
          if not dependent_task or dependent_task["status"] != "complete":
              all_dependent_tasks_complete = False
              break
         
    # Execute task
    print("\033[92m\033[1m"+"\n*****NEXT TASK*****\n"+"\033[0m\033[0m")
    print(str(task['id'])+": "+str(task['task'])+" ["+str(task['tool']+"]"))
    task_prompt = f"Complete your assigned task based on the objective and only based on information provided in the dependent task output, if provided. Process in {LANGUAGE}. Your objective: {OBJECTIVE}. Your task: {task['task']}"
    if task["dependent_task_ids"]:
      dependent_tasks_output = ""
      for dep_id in task["dependent_task_ids"]:
          dependent_task_output = get_task_by_id(dep_id)["output"]
          dependent_task_output = dependent_task_output[0:2000]
          dependent_tasks_output += f" {dependent_task_output}"
      task_prompt += f" Your dependent tasks output: {dependent_tasks_output}\n OUTPUT:"

    # Use tool to complete the task
    if task["tool"] == "text-completion":
        task_output = text_completion_tool(task_prompt)
    elif task["tool"] == "web-search":
        task_output = web_search_tool(str(task['task']))
    elif task["tool"] == "web-scrape":
        task_output = web_scrape_tool(str(task['task']))

    # Find task index in the task_list
    task_index = next((i for i, t in enumerate(task_list) if t["id"] == task["id"]), None)

    # Mark task as complete and save output
    task_list[task_index]["status"] = "complete"
    task_list[task_index]["output"] = task_output

    # Print task output
    print("\033[93m\033[1m"+"\nTask Output:"+"\033[0m\033[0m")
    print(task_output)

    # Add task output to session_summary
    global session_summary
    session_summary += f"\n\nTask {task['id']} - {task['task']}:\n{task_output}"

task_list = []

def task_creation_agent(objective: str) -> List[Dict]:
    global task_list
    minified_task_list = [{k: v for k, v in task.items() if k != "result"} for task in task_list]

    prompt = (
        f"You are a task creation AI tasked with creating a list of tasks as a array in JSON format, considering the ultimate objective of your team: {OBJECTIVE}. "
        f"Create new tasks based on the objective. Limit tasks types to those that can be completed with the available tools listed below. Task description should be detailed."
        f"Current tool option is [text-completion] {websearch_var} and only.\n"
        f"[text-completion]: Useful for summarizing, discussing, criticizing, considering and evaluating \n"
        f"[web-search]: Useful for searching and getting information on the net.\n"
        f"dependent_task_ids should always be an empty array, or an array of numbers representing the task ID it should pull results from."
        f"Make sure all task IDs are in chronological order.\n"
        f"The last step is always to provide a final summary report including tasks executed and summary of knowledge acquired.\n"
        f"Answer in {LANGUAGE}.\n"
        f"An example of the desired output JSON format is: "
        "[{\"id\": 1, \"task\": \"https://untapped.vc\", \"tool\": \"web-scrape\", \"dependent_task_ids\": [], \"status\": \"incomplete\", \"result\": null, \"result_summary\": null}, {\"id\": 2, \"task\": \"Consider additional insights that can be reasoned from the results of...\", \"tool\": \"text-completion\", \"dependent_task_ids\": [1], \"status\": \"incomplete\", \"result\": null, \"result_summary\": null}, {\"id\": 3, \"task\": \"Untapped Capital\", \"tool\": \"web-search\", \"dependent_task_ids\": [], \"status\": \"incomplete\", \"result\": null, \"result_summary\": null}].\n"
        f"JSON TASK LIST="
    )

    print("\033[90m\033[3m" + "\nInitializing...\n" + "\033[0m")
    print("\033[90m\033[3m" + "Analyzing objective...\n" + "\033[0m")
    print("\033[90m\033[3m" + "Running task creation agent...\n" + "\033[0m")

    messages=[
        {"role": "system",
         "content": "Task creation AI. Provide your response in JSON format."
        },
        {"role": "user",
         "content": prompt
        }
    ]

    response = call_llm(messages=messages, temperature=0)

    # Extract the content of the assistant's response and parse it as JSON
    result = response["choices"][0]["message"]["content"]
    print("\033[90m\033[3m" + "\nDone!\n" + "\033[0m")
    try:
        task_list = json.loads(result)
    except Exception as error:
        print(error)

    return task_list

##### START MAIN LOOP########

#Print OBJECTIVE
print("\033[96m\033[1m"+"\n*****OBJECTIVE*****\n"+"\033[0m\033[0m")
print(OBJECTIVE)

# Initialize task_id_counter
task_id_counter = 1

# Run the task_creation_agent to create initial tasks
task_list = task_creation_agent(OBJECTIVE)
print_tasklist()

# Execute tasks in order
if len(task_list) > 0:
    for task in task_list:
        if task["status"] == "incomplete":
            execute_task(task, task_list, OBJECTIVE)
            print_tasklist()

# Print session summary
print("\033[96m\033[1m"+"\n*****SESSION SUMMARY*****\n"+"\033[0m\033[0m")
print(session_summary)
