import requests

from typing import List
from agent_modules.database.types.search_result import SerperSearchResult

class PerserSearchService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def search(self, query: str) -> str:
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        response = requests.post(
            "https://google.serper.dev/search",
            headers=headers,
            params={"q": query, "num": 20}
        )
        response.raise_for_status()
        return self._parse_response(response.json())
        
    def _parse_response(self, results: dict) -> str:
        snippets = self._parse_snippets(results)
        return snippets
    
    def _parse_snippets(self, results: dict) -> List[str]:
        search_results = []

        # Don't need to get the direct answer from the answer box
        if results.get("answerBox"):
            answer_box = results.get("answerBox", {})
            answer_box_title = answer_box.get("title")
            answer_box_link = answer_box.get("link")
            
            if answer_box.get("answer"):
                return [SerperSearchResult(title=answer_box_title, link=answer_box_link, search_text=answer_box.get("answer"))]
            elif answer_box.get("snippet"):
                return [SerperSearchResult(title=answer_box_title, link=answer_box_link, search_text=answer_box.get("snippet").replace("\n", " "))]
            elif answer_box.get("snippetHighlighted"):
                return [SerperSearchResult(title=answer_box_title, link=answer_box_link, search_text=answer_box.get("snippetHighlighted").replace("\n", " "))]

        if results.get("knowledgeGraph"):
            kg = results.get("knowledgeGraph", {})
            result_title = None
            result_snippets = []
            result_link = None

            title = kg.get("title")
            entity_type = kg.get("type")
            if entity_type:
                result_snippets.append(f"{title}: {entity_type}.")
            description = kg.get("description")
            if description:
                result_snippets.append(description)
            for attribute, value in kg.get("attributes", {}).items():
                result_snippets.append(f"{title} {attribute}: {value}.")

            if kg.get("website"):
                result_link = kg.get("website")

    
            search_results.append(SerperSearchResult(title=result_title, link=result_link, search_text="\n".join(result_snippets)))

        # This provdies a lot of hallucinated search results
        if len(search_results) == 0 and results.get("organic"):
            organic = results.get("organic", [])
            title = None
            snippet = None
            link = None

            for result in organic[:5]:
                if "snippet" in result:
                    snippet = result["snippet"]
                if "title" in result:
                    title = result["title"]
                if "link" in result:
                    link = result["link"]
                search_results.append(SerperSearchResult(title=title, link=link, search_text=snippet))

        if len(search_results) == 0:
            print("No good Google Search Result was found")
        return search_results
