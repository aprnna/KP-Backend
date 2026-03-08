---
trigger: always_on
---

1. Follow PEP8 standards.
2. Maximum line length: 100 characters.
3. Use type hints for all public functions and methods.
   Example:
   async def scrape_author(author: str, year: int) -> list[dict]:

4.Use descriptive variable names.
Avoid:
data, x, result1
Prefer:
author_results
article_batch
scrape_duration

5. Do not create deeply nested functions.
   Maximum recommended nesting depth: 3.

6. Use explicit imports instead of wildcard imports.
   Correct:
   from app.services.scraper.base import BaseScraper
   Incorrect:
   from scraper import \*

7.Prefer f-strings for string formatting.
Correct:
f"Scraping author {author_name}"
Incorrect:
"Scraping author {}".format(author_name)

8.Use consistent logging style.
Example:
logger.info("scrape_author_start", extra={"author": author_name})
