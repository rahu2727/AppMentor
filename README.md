# AppMentor
### AI knowledge assistant for enterprise applications

> Ask AppMentor anything about your codebase.
> Get a different answer depending on who you are.

![Sprint 1 — ERPNext Knowledge Base](screenshot.png)

## What it does
AppMentor reads your enterprise codebase and documentation,
stores it in a local vector database, and answers questions
in plain English — differently for each role:
- End User gets step-by-step guidance
- Business User gets process and policy detail  
- Manager gets high-level overview
- Developer gets technical detail and code references

## What is built so far
- Sprint 1 (complete): ReAct agent + ChromaDB knowledge base
- Sprint 2 (next): LangGraph 4-agent pipeline + 5 personas
- Sprint 3: Streamlit chat UI
- Sprint 4: MCP tool servers
- Sprint 5: Microsoft Teams + browser extension

## Quick start (under 30 minutes)

### Prerequisites
- Python 3.11 or higher
- Git
- An Anthropic API key (console.anthropic.com)
- A Tavily API key (app.tavily.com — free)

### 1. Clone and set up
```
git clone https://github.com/rahu2727/AppMentor.git
cd AppMentor
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Add your API keys
```
cp .env.example .env
# Open .env and replace placeholder values with your real keys
```

### 3. Build the knowledge base
```
python week2/ingest.py --source forum
python week2/ingest.py --source docs
python week2/ingest.py --source code
```

Note: First run downloads embedding model (~90MB, once only)
Code ingestion clones ERPNext repo (~400MB, once only)

### 4. Run AppMentor
```
streamlit run app.py
# Opens at http://localhost:8501
```

## Try these questions
- "How do I submit an expense claim?"
- "What happens if my leave approver is on leave?"
- "What is the difference between a Purchase Order and a Material Request?"

## Security
- Your .env file is excluded by .gitignore
- Your API keys never leave your machine during ingestion
- ChromaDB runs locally — your data stays on your system
- Only the final answer generation calls the Anthropic API

## Tech stack
- Python · Anthropic Claude · LangGraph · ChromaDB
- Sentence Transformers · Streamlit · Tavily Search
- Open source · MIT License

## Built by
Rahul Chaudhary
SAP ABAP and Fiori developer — first AI project
Building in public, one sprint at a time.
github.com/rahu2727/AppMentor
