import os
import json
import shutil
from app.config import DATA_DIR

DOCUMENTS_DIR = os.path.join(DATA_DIR, "documents")
CATALOG_PATH = os.path.join(DOCUMENTS_DIR, "documents.json")

os.makedirs(DOCUMENTS_DIR, exist_ok=True)


class DocumentManager:
    """Manages a catalog of Markdown and PDF documents."""

    def _load_catalog(self):
        if not os.path.isfile(CATALOG_PATH):
            return {"categories": {}, "documents": []}
        with open(CATALOG_PATH, "r") as f:
            return json.load(f)

    def _save_catalog(self, catalog):
        with open(CATALOG_PATH, "w") as f:
            json.dump(catalog, f, indent=2)

    def list_documents(self):
        """Return the full catalog."""
        return self._load_catalog()

    def add_document(self, name: str, category: str, filename: str):
        """Register a document in the catalog (file must already exist)."""
        catalog = self._load_catalog()
        rel_path = f"files/{filename}"
        full_path = os.path.join(DOCUMENTS_DIR, rel_path)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"File not found: {filename}")
        # Check for duplicate name in same category
        for doc in catalog["documents"]:
            if doc["name"] == name and doc["category"] == category:
                raise FileExistsError(f"Document '{name}' already exists in '{category}'")
        catalog["documents"].append({
            "name": name,
            "category": category,
            "location": rel_path,
        })
        # Auto-create category entry if needed
        if category and category not in catalog["categories"]:
            catalog["categories"][category] = {}
        self._save_catalog(catalog)
        return {"name": name, "category": category, "location": rel_path}

    def remove_document(self, name: str, category: str):
        """Remove a document from the catalog and optionally delete the file."""
        catalog = self._load_catalog()
        found = None
        for i, doc in enumerate(catalog["documents"]):
            if doc["name"] == name and doc["category"] == category:
                found = i
                break
        if found is None:
            raise FileNotFoundError(f"Document '{name}' not found in '{category}'")
        removed = catalog["documents"].pop(found)
        # Remove file if it exists
        full_path = os.path.join(DOCUMENTS_DIR, removed["location"])
        if os.path.isfile(full_path):
            os.remove(full_path)
        # Remove category if empty
        if category:
            remaining = [d for d in catalog["documents"] if d["category"] == category]
            if not remaining:
                catalog["categories"].pop(category, None)
        self._save_catalog(catalog)
        return {"removed": removed}

    def list_categories(self):
        """Return list of category names."""
        catalog = self._load_catalog()
        cats = set()
        for doc in catalog["documents"]:
            if doc.get("category"):
                cats.add(doc["category"])
        return sorted(cats)

    def rename_document(self, name: str, category: str, new_name: str):
        """Rename a document in the catalog."""
        catalog = self._load_catalog()
        for doc in catalog["documents"]:
            if doc["name"] == name and doc["category"] == category:
                doc["name"] = new_name
                self._save_catalog(catalog)
                return doc
        raise FileNotFoundError(f"Document '{name}' not found in '{category}'")

    def ensure_files_dir(self):
        """Ensure the files subdirectory exists."""
        files_dir = os.path.join(DOCUMENTS_DIR, "files")
        os.makedirs(files_dir, exist_ok=True)
        return files_dir
