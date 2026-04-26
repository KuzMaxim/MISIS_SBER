from __future__ import annotations

from pathlib import Path

from app.safety import SAFE_DISCLAIMER
from app.storage import load_json_file
from app.utils import haversine_km, normalize_medication_name


class PharmacyService:
    def __init__(self, pharmacy_file: Path):
        self.pharmacies = load_json_file(pharmacy_file)

    def search(
        self,
        drug_name: str,
        *,
        user_lat: float | None = None,
        user_lon: float | None = None,
        limit: int = 5,
    ) -> dict:
        normalized = normalize_medication_name(drug_name)
        results: list[dict] = []

        for pharmacy in self.pharmacies:
            for item in pharmacy["items"]:
                if normalize_medication_name(item["drug_name"]) != normalized:
                    continue

                distance = None
                if user_lat is not None and user_lon is not None:
                    distance = round(
                        haversine_km(user_lat, user_lon, pharmacy["lat"], pharmacy["lon"]),
                        2,
                    )

                results.append(
                    {
                        "pharmacy_name": pharmacy["pharmacy_name"],
                        "address": pharmacy["address"],
                        "price": item["price"],
                        "in_stock": item["in_stock"],
                        "distance_km": distance,
                    }
                )

        results.sort(
            key=lambda item: (
                not item["in_stock"],
                item["price"],
                item["distance_km"] if item["distance_km"] is not None else 10**6,
            )
        )
        return {
            "drug_name": drug_name,
            "results": results[:limit],
            "disclaimer": SAFE_DISCLAIMER,
        }

