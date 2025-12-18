#!/usr/bin/env python3
"""Test script for aurora_search functionality."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from aurora_mcp.server import aurora_search, get_embedding_service
from aurora_mcp.database import init_engine


async def test_search():
    """Test aurora_search with various parameters."""
    print("=" * 60)
    print("Testing aurora_search")
    print("=" * 60)

    # Initialize database
    print("\n1. Initializing database engine...")
    try:
        await init_engine()
        print("✓ Database engine initialized")
    except Exception as e:
        print(f"✗ Failed to initialize database: {e}")
        return

    # Test embedding service
    print("\n2. Testing embedding service...")
    try:
        embedding_service = await get_embedding_service()
        test_embedding = await embedding_service.embed("test query")
        print(f"✓ Embedding service working (dimension: {len(test_embedding)})")
    except Exception as e:
        print(f"✗ Embedding service failed: {e}")
        return

    # Test basic search
    print("\n3. Testing basic search...")
    try:
        result = await aurora_search(
            query="test query",
            limit=5,
            threshold=0.0  # Lower threshold to get any results
        )
        print(f"✓ Search completed")
        print(f"  Total found: {result['total_found']}")
        print(f"  Query: {result['query']}")

        if result['documents']:
            print("\n  Top results:")
            for i, doc in enumerate(result['documents'][:3], 1):
                print(f"    {i}. ID: {doc['id']}")
                print(f"       Type: {doc['document_type']}")
                print(f"       Namespace: {doc['namespace']}")
                print(f"       Similarity: {doc['similarity_score']:.4f}")
                print(f"       Content preview: {doc['content'][:100]}...")
        else:
            print("  No documents found (database might be empty)")
    except Exception as e:
        print(f"✗ Search failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test search with namespace filter
    print("\n4. Testing search with namespace filter...")
    try:
        result = await aurora_search(
            query="test",
            namespace="default",
            limit=3,
            threshold=0.0
        )
        print(f"✓ Namespace filter search completed")
        print(f"  Total found: {result['total_found']}")
    except Exception as e:
        print(f"✗ Namespace filter search failed: {e}")

    # Test search with document_type filter
    print("\n5. Testing search with document_type filter...")
    try:
        result = await aurora_search(
            query="test",
            document_type="conversation",
            limit=3,
            threshold=0.0
        )
        print(f"✓ Document type filter search completed")
        print(f"  Total found: {result['total_found']}")
    except Exception as e:
        print(f"✗ Document type filter search failed: {e}")

    # Test search with metadata filters
    print("\n6. Testing search with metadata filters...")
    try:
        result = await aurora_search(
            query="test",
            metadata_filters={"source": "claude_code"},
            limit=3,
            threshold=0.0
        )
        print(f"✓ Metadata filter search completed")
        print(f"  Total found: {result['total_found']}")
    except Exception as e:
        print(f"✗ Metadata filter search failed: {e}")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_search())
