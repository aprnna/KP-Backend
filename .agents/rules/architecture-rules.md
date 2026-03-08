---
trigger: always_on
---

1. Respect the project layer structure.

Allowed responsibilities:
API layer

- Request validation
- Authentication
- Triggering service calls

Service layer

- Business logic
- Scraping orchestration
- Data transformation

Scraper layer

- External API communication
- Pagination
- Retry logic

Model layer

- ORM definitions only

- API routes must never contain scraping logic.

Incorrect:
router.post("/scrape")
async def scrape():
await crossref_scraper.scrape(...)

Correct:
router.post("/scrape")
async def scrape():
await scraping_service.run_scraping_job(...)

3. Services must not depend on API modules.
   Dependency direction must always be:
   api → services → scrapers → models

4. Scrapers must be stateless except for HTTP client lifecycle.

5. Do not create circular dependencies between modules.
