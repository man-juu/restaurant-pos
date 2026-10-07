from fastapi import FastAPI

app = FastAPI(title="Restaurant POS API")


@app.get("/health")
async def health() -> dict[str, str]:
    # Placeholder; slice 0.2 adds the database check (FR-X-004 / NFR-010).
    return {"status": "ok"}
