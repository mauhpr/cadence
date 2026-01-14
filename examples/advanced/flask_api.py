"""
Flask Integration Example - Product Catalog API

This example demonstrates using Cadence with Flask to build
a product catalog API with search, filtering, and enrichment.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from flask import Flask, jsonify, request

from cadence import Cadence, Score, note, retry, timeout, fallback
from cadence.integrations.flask import CadenceBlueprint, cadence_route


# --- Score Definitions ---


@dataclass
class ProductSearchScore(Score):
    """Score for product search cadence."""
    query: str
    category: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    page: int = 1
    limit: int = 20

    # Populated by notes
    products: List[Dict[str, Any]] = field(default_factory=list)
    total_count: int = 0
    facets: Optional[Dict[str, Any]] = None


@dataclass
class ProductDetailScore(Score):
    """Score for product detail cadence."""
    product_id: str

    # Populated by notes
    product: Optional[Dict[str, Any]] = None
    reviews: List[Dict[str, Any]] = field(default_factory=list)
    related: List[Dict[str, Any]] = field(default_factory=list)
    inventory: Optional[Dict[str, Any]] = None


# --- Mock Services ---


class ProductService:
    """Mock product database service."""

    PRODUCTS = [
        {"id": "1", "name": "Laptop Pro", "category": "electronics", "price": 1299.99},
        {"id": "2", "name": "Wireless Mouse", "category": "electronics", "price": 49.99},
        {"id": "3", "name": "Coffee Maker", "category": "home", "price": 89.99},
        {"id": "4", "name": "Running Shoes", "category": "sports", "price": 129.99},
    ]

    async def search(
        self,
        query: str,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.02)  # Simulate latency
        results = [p for p in self.PRODUCTS if query.lower() in p["name"].lower()]
        if category:
            results = [p for p in results if p["category"] == category]
        if min_price:
            results = [p for p in results if p["price"] >= min_price]
        if max_price:
            results = [p for p in results if p["price"] <= max_price]
        return results

    async def get_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        await asyncio.sleep(0.01)
        for p in self.PRODUCTS:
            if p["id"] == product_id:
                return p
        return None

    async def get_related(self, product_id: str) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.03)
        product = await self.get_by_id(product_id)
        if not product:
            return []
        return [p for p in self.PRODUCTS if p["category"] == product["category"] and p["id"] != product_id]


class ReviewService:
    """Mock review service."""

    async def get_reviews(self, product_id: str) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.02)
        return [
            {"id": "r1", "rating": 5, "comment": "Excellent product!"},
            {"id": "r2", "rating": 4, "comment": "Good value for money."},
        ]


class InventoryService:
    """Mock inventory service."""

    async def check_stock(self, product_id: str) -> Dict[str, Any]:
        await asyncio.sleep(0.015)
        return {"product_id": product_id, "in_stock": True, "quantity": 42}


class FacetService:
    """Mock facet/filter service."""

    async def get_facets(self, query: str) -> Dict[str, Any]:
        await asyncio.sleep(0.01)
        return {
            "categories": [
                {"name": "electronics", "count": 2},
                {"name": "home", "count": 1},
                {"name": "sports", "count": 1},
            ],
            "price_ranges": [
                {"min": 0, "max": 50, "count": 1},
                {"min": 50, "max": 100, "count": 1},
                {"min": 100, "max": 500, "count": 1},
                {"min": 500, "max": 2000, "count": 1},
            ],
        }


# Initialize services
product_svc = ProductService()
review_svc = ReviewService()
inventory_svc = InventoryService()
facet_svc = FacetService()


# --- Search Cadence Notes ---


@note
@retry(max_attempts=3, backoff="exponential")
@timeout(2.0)
async def search_products(score: ProductSearchScore) -> None:
    """Search for products matching the query."""
    score.products = await product_svc.search(
        query=score.query,
        category=score.category,
        min_price=score.min_price,
        max_price=score.max_price,
    )
    score.total_count = len(score.products)


@note
@timeout(1.0)
@fallback({})
async def fetch_facets(score: ProductSearchScore) -> None:
    """Fetch facets for filtering UI."""
    score.facets = await facet_svc.get_facets(score.query)


# --- Detail Cadence Notes ---


@note
@retry(max_attempts=2)
@timeout(1.0)
async def fetch_product(score: ProductDetailScore) -> None:
    """Fetch product details."""
    score.product = await product_svc.get_by_id(score.product_id)
    if score.product is None:
        raise ValueError(f"Product not found: {score.product_id}")


@note
@timeout(2.0)
@fallback([])
async def fetch_reviews(score: ProductDetailScore) -> None:
    """Fetch product reviews."""
    score.reviews = await review_svc.get_reviews(score.product_id)


@note
@timeout(2.0)
@fallback([])
async def fetch_related(score: ProductDetailScore) -> None:
    """Fetch related products."""
    score.related = await product_svc.get_related(score.product_id)


@note
@timeout(1.0)
@fallback({"in_stock": False, "quantity": 0})
async def check_inventory(score: ProductDetailScore) -> None:
    """Check product inventory."""
    score.inventory = await inventory_svc.check_stock(score.product_id)


# --- Cadence Definitions ---


def create_search_cadence(score: ProductSearchScore) -> Cadence[ProductSearchScore]:
    """Create a product search cadence."""
    return (
        Cadence("product_search", score)
        .sync("fetch_data", [
            search_products,
            fetch_facets,
        ])
    )


def create_detail_cadence(score: ProductDetailScore) -> Cadence[ProductDetailScore]:
    """Create a product detail cadence."""
    return (
        Cadence("product_detail", score)
        .then("fetch_product", fetch_product)
        .sync("enrich", [
            fetch_reviews,
            fetch_related,
            check_inventory,
        ])
    )


# --- Flask Application ---


app = Flask(__name__)

# Create a blueprint for product routes
products_bp = CadenceBlueprint("products", __name__, url_prefix="/api/products")


@products_bp.route("/search")
def search():
    """Search products endpoint."""
    # Build score from query params
    score = ProductSearchScore(
        query=request.args.get("q", ""),
        category=request.args.get("category"),
        min_price=float(request.args.get("min_price")) if request.args.get("min_price") else None,
        max_price=float(request.args.get("max_price")) if request.args.get("max_price") else None,
        page=int(request.args.get("page", 1)),
        limit=int(request.args.get("limit", 20)),
    )

    # Run the cadence
    cadence = create_search_cadence(score)
    result = asyncio.run(cadence.run())

    return jsonify({
        "query": result.query,
        "products": result.products,
        "total": result.total_count,
        "facets": result.facets,
        "page": result.page,
        "limit": result.limit,
    })


@products_bp.route("/<product_id>")
def get_product(product_id: str):
    """Get product details endpoint."""
    score = ProductDetailScore(product_id=product_id)

    try:
        cadence = create_detail_cadence(score)
        result = asyncio.run(cadence.run())

        return jsonify({
            "product": result.product,
            "reviews": result.reviews,
            "related": result.related,
            "inventory": result.inventory,
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


# Register blueprint
app.register_blueprint(products_bp)


# Health check endpoint
@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


# --- Main ---


if __name__ == "__main__":
    print("Starting Flask Product Catalog API...")
    print("Endpoints:")
    print("  GET /api/products/search?q=<query>")
    print("  GET /api/products/<product_id>")
    print("  GET /health")
    print()
    app.run(debug=True, port=5000)
