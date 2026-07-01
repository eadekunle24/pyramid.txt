import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from dropship_automation.suppliers.base import SupplierProduct


@dataclass
class ListingCopy:
    title: str
    description_html: str
    tags: list[str]


class ContentGenerator(ABC):
    @abstractmethod
    def generate_listing_copy(self, product: SupplierProduct) -> ListingCopy:
        ...


class TemplateContentGenerator(ContentGenerator):
    """Deterministic, no-API-key-required copy generator. Used when no
    ANTHROPIC_API_KEY is configured, or as a fallback if the AI call fails."""

    def generate_listing_copy(self, product: SupplierProduct) -> ListingCopy:
        title = product.title.strip()
        bullets = "".join(
            f"<li>{point}</li>"
            for point in [
                product.description.strip().rstrip("."),
                f"Category: {product.category}",
                "Ships worldwide with tracked delivery",
            ]
        )
        description_html = f"<p>{product.description.strip()}</p><ul>{bullets}</ul>"
        tags = list({product.category, "trending", "free-shipping"})
        return ListingCopy(title=title, description_html=description_html, tags=tags)


class ClaudeContentGenerator(ContentGenerator):
    """Uses the Claude API to write on-brand product titles/descriptions/tags.
    Falls back to the template generator if the API call fails for any reason,
    so a transient AI outage never blocks the automation pipeline."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._fallback = TemplateContentGenerator()

    def generate_listing_copy(self, product: SupplierProduct) -> ListingCopy:
        prompt = (
            "Write ecommerce listing copy for this dropshipped product. "
            "Respond with ONLY a JSON object with keys: title, description_html, tags (array of 3-6 lowercase strings). "
            f"Product name: {product.title}\n"
            f"Raw supplier description: {product.description}\n"
            f"Category: {product.category}\n"
        )
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            match = re.search(r"\{.*\}", text, re.DOTALL)
            data = json.loads(match.group(0) if match else text)
            return ListingCopy(
                title=data["title"],
                description_html=data["description_html"],
                tags=list(data["tags"]),
            )
        except Exception:
            return self._fallback.generate_listing_copy(product)


def get_content_generator(anthropic_api_key: str | None) -> ContentGenerator:
    if anthropic_api_key:
        return ClaudeContentGenerator(anthropic_api_key)
    return TemplateContentGenerator()
