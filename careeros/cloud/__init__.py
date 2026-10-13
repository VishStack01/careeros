"""CareerOS Cloud: the multi-user service.

One shared job inventory, read from the hourly scan, serves every account.
Everything about a person (filters, pipeline, application details, resume,
history) is keyed by their user id and never crosses accounts.

  careeros cloud migrate     apply database migrations
  careeros cloud serve       the web app and API (FastAPI)
  careeros cloud worker      ingestion, per-user matching, email, cleanup

Install with `pip install "careeros[cloud]"`. See docs/cloud.md.
"""
