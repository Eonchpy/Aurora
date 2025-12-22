#!/usr/bin/env python3
"""Backfill brief_summary for existing documents in AuroraKB.

This script generates summaries for documents that don't have them yet.
It processes documents in batches with rate limiting to avoid API quota issues.

Usage:
    uv run python scripts/backfill_summaries.py [--batch-size 10] [--delay 6] [--namespace default]

Options:
    --batch-size: Number of documents to process per batch (default: 10)
    --delay: Delay in seconds between batches (default: 6, ~10 docs/minute)
    --namespace: Only process documents in this namespace (optional)
    --dry-run: Preview what would be done without making changes
"""

from __future__ import annotations

import asyncio
import argparse
import logging
import sys
import time
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aurora_mcp.config import get_settings
from aurora_mcp.database import get_session, init_engine
from aurora_mcp.models import Document
from aurora_mcp.services.summarizer import Summarizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BackfillProgress:
    """Track backfill progress and statistics."""

    def __init__(self):
        self.total_documents = 0
        self.processed = 0
        self.succeeded = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = time.time()

    def log_progress(self):
        """Log current progress."""
        elapsed = time.time() - self.start_time
        rate = self.processed / elapsed if elapsed > 0 else 0
        logger.info(
            f"Progress: {self.processed}/{self.total_documents} "
            f"(Success: {self.succeeded}, Failed: {self.failed}, Skipped: {self.skipped}) "
            f"Rate: {rate:.2f} docs/sec"
        )

    def log_final(self):
        """Log final statistics."""
        elapsed = time.time() - self.start_time
        logger.info("=" * 60)
        logger.info("Backfill Complete!")
        logger.info(f"Total documents: {self.total_documents}")
        logger.info(f"Processed: {self.processed}")
        logger.info(f"Succeeded: {self.succeeded}")
        logger.info(f"Failed: {self.failed}")
        logger.info(f"Skipped: {self.skipped}")
        logger.info(f"Total time: {elapsed:.2f} seconds")
        logger.info(f"Average rate: {self.processed / elapsed:.2f} docs/sec")
        logger.info("=" * 60)


async def count_documents_without_summary(
    session: AsyncSession,
    namespace: str | None = None
) -> int:
    """Count documents that need summaries."""
    stmt = select(func.count(Document.id)).where(Document.brief_summary.is_(None))
    if namespace:
        stmt = stmt.where(Document.namespace == namespace)
    result = await session.execute(stmt)
    return result.scalar_one()


async def fetch_documents_batch(
    session: AsyncSession,
    batch_size: int,
    namespace: str | None = None
) -> list[Document]:
    """Fetch a batch of documents without summaries."""
    stmt = (
        select(Document)
        .where(Document.brief_summary.is_(None))
        .order_by(Document.created_at.asc())  # Process oldest first
        .limit(batch_size)
    )
    if namespace:
        stmt = stmt.where(Document.namespace == namespace)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def generate_summary_for_document(
    doc: Document,
    summarizer: Summarizer,
    session: AsyncSession,
    dry_run: bool = False
) -> bool:
    """Generate and save summary for a single document.

    Returns:
        True if successful, False otherwise
    """
    try:
        # Generate summary
        summary = await summarizer.summarize(doc.content)

        if not summary:
            logger.warning(f"Failed to generate summary for document {doc.id}")
            return False

        if dry_run:
            logger.info(
                f"[DRY RUN] Would update document {doc.id} with summary: "
                f"{summary[:100]}..."
            )
            return True

        # Update document
        doc.brief_summary = summary
        session.add(doc)
        await session.commit()

        logger.debug(
            f"Generated summary for document {doc.id}: "
            f"{len(doc.content)} chars -> {len(summary)} chars"
        )
        return True

    except Exception as exc:
        logger.error(f"Error processing document {doc.id}: {exc}", exc_info=True)
        return False


async def backfill_summaries(
    batch_size: int = 10,
    delay: float = 6.0,
    namespace: str | None = None,
    dry_run: bool = False
):
    """Main backfill function."""
    # Initialize
    settings = get_settings()

    # Validate configuration
    if not settings.summarization_model:
        logger.error(
            "SUMMARIZATION_MODEL not configured. "
            "Please set environment variable and try again."
        )
        return

    logger.info("Starting backfill process...")
    logger.info(f"Configuration:")
    logger.info(f"  Model: {settings.summarization_model}")
    logger.info(f"  Batch size: {batch_size}")
    logger.info(f"  Delay: {delay}s between batches")
    logger.info(f"  Namespace filter: {namespace or 'None (all namespaces)'}")
    logger.info(f"  Dry run: {dry_run}")

    # Initialize services
    await init_engine()
    summarizer = Summarizer(
        model=settings.summarization_model,
        base_url=settings.summarization_base_url or settings.query_expansion_base_url or settings.openai_base_url,
        api_key=settings.summarization_api_key or settings.query_expansion_api_key or settings.openai_api_key,
        temperature=settings.summarization_temperature,
        max_tokens=settings.summarization_max_tokens,
    )

    progress = BackfillProgress()

    # Count total documents
    async for session in get_session():
        progress.total_documents = await count_documents_without_summary(session, namespace)
        logger.info(f"Found {progress.total_documents} documents without summaries")

        if progress.total_documents == 0:
            logger.info("No documents to process. Exiting.")
            return

        # Process in batches
        while progress.processed < progress.total_documents:
            # Fetch batch
            documents = await fetch_documents_batch(session, batch_size, namespace)

            if not documents:
                logger.info("No more documents to process")
                break

            logger.info(f"Processing batch of {len(documents)} documents...")

            # Process each document in batch
            for doc in documents:
                success = await generate_summary_for_document(
                    doc, summarizer, session, dry_run
                )

                progress.processed += 1
                if success:
                    progress.succeeded += 1
                else:
                    progress.failed += 1

            # Log progress
            progress.log_progress()

            # Rate limiting: delay between batches
            if progress.processed < progress.total_documents:
                logger.info(f"Waiting {delay}s before next batch...")
                await asyncio.sleep(delay)

    # Final statistics
    progress.log_final()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill brief_summary for existing AuroraKB documents"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of documents to process per batch (default: 10)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=6.0,
        help="Delay in seconds between batches (default: 6, ~10 docs/minute)"
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default=None,
        help="Only process documents in this namespace (optional)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be done without making changes"
    )

    args = parser.parse_args()

    try:
        asyncio.run(backfill_summaries(
            batch_size=args.batch_size,
            delay=args.delay,
            namespace=args.namespace,
            dry_run=args.dry_run
        ))
    except KeyboardInterrupt:
        logger.info("\nBackfill interrupted by user")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"Backfill failed: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
