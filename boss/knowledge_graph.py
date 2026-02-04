"""Bi-temporal knowledge graph for tracking facts and discoveries over time"""

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Literal
from uuid import uuid4


@dataclass
class Entity:
    """An entity with bi-temporal tracking

    Attributes:
        id: Unique identifier for the entity
        entity_type: Type of entity (e.g., 'dci_job', 'jira_ticket', 'component')
        valid_from: When the fact became true in reality
        valid_to: When the fact stopped being true (None if still valid)
        tx_from: When BOSS learned about the fact
        tx_to: When BOSS stopped believing the fact (None if current belief)
        data: Flexible JSON data for the entity
    """
    id: str
    entity_type: str
    valid_from: datetime
    valid_to: Optional[datetime]
    tx_from: datetime
    tx_to: Optional[datetime]
    data: dict[str, Any]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "tx_from": self.tx_from.isoformat(),
            "tx_to": self.tx_to.isoformat() if self.tx_to else None,
            "data": self.data
        }

    @classmethod
    def from_row(cls, row: tuple) -> "Entity":
        """Create Entity from database row"""
        return cls(
            id=row[0],
            entity_type=row[1],
            valid_from=datetime.fromisoformat(row[2]),
            valid_to=datetime.fromisoformat(row[3]) if row[3] else None,
            tx_from=datetime.fromisoformat(row[4]),
            tx_to=datetime.fromisoformat(row[5]) if row[5] else None,
            data=json.loads(row[6])
        )


@dataclass
class Relationship:
    """A relationship between entities with bi-temporal tracking

    Attributes:
        id: Unique identifier for the relationship
        rel_type: Type of relationship (e.g., 'job_uses_component', 'ticket_references_job')
        source_id: ID of the source entity
        target_id: ID of the target entity
        valid_from: When the relationship became true
        valid_to: When the relationship stopped being true (None if still valid)
        tx_from: When BOSS learned about the relationship
        tx_to: When BOSS stopped believing it (None if current belief)
        properties: Additional properties for the relationship
    """
    id: str
    rel_type: str
    source_id: str
    target_id: str
    valid_from: datetime
    valid_to: Optional[datetime]
    tx_from: datetime
    tx_to: Optional[datetime]
    properties: dict[str, Any]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "rel_type": self.rel_type,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "tx_from": self.tx_from.isoformat(),
            "tx_to": self.tx_to.isoformat() if self.tx_to else None,
            "properties": self.properties
        }

    @classmethod
    def from_row(cls, row: tuple) -> "Relationship":
        """Create Relationship from database row"""
        return cls(
            id=row[0],
            rel_type=row[1],
            source_id=row[2],
            target_id=row[3],
            valid_from=datetime.fromisoformat(row[4]),
            valid_to=datetime.fromisoformat(row[5]) if row[5] else None,
            tx_from=datetime.fromisoformat(row[6]),
            tx_to=datetime.fromisoformat(row[7]) if row[7] else None,
            properties=json.loads(row[8]) if row[8] else {}
        )


class KnowledgeGraph:
    """Bi-temporal knowledge graph storage engine"""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the knowledge graph

        Args:
            db_path: Path to SQLite database file. If None, uses ~/.boss/knowledge_graph.db
                    If ":memory:", uses in-memory database for testing
        """
        if db_path is None:
            db_path = str(Path.home() / ".boss" / "knowledge_graph.db")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._create_schema()

    def _create_schema(self):
        """Create database schema if it doesn't exist"""
        cursor = self.conn.cursor()

        # Entities table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                valid_from TIMESTAMP NOT NULL,
                valid_to TIMESTAMP,
                tx_from TIMESTAMP NOT NULL,
                tx_to TIMESTAMP,
                data JSON NOT NULL
            )
        """)

        # Indexes for temporal queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_entities_type
            ON entities(entity_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_entities_valid_time
            ON entities(valid_from, valid_to)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_entities_tx_time
            ON entities(tx_from, tx_to)
        """)

        # Relationships table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id TEXT PRIMARY KEY,
                rel_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                valid_from TIMESTAMP NOT NULL,
                valid_to TIMESTAMP,
                tx_from TIMESTAMP NOT NULL,
                tx_to TIMESTAMP,
                properties JSON,
                FOREIGN KEY (source_id) REFERENCES entities(id),
                FOREIGN KEY (target_id) REFERENCES entities(id)
            )
        """)

        # Indexes for relationship queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_type
            ON relationships(rel_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_source
            ON relationships(source_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_target
            ON relationships(target_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_valid_time
            ON relationships(valid_from, valid_to)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_tx_time
            ON relationships(tx_from, tx_to)
        """)

        self.conn.commit()

    def insert_entity(
        self,
        entity_type: str,
        data: dict[str, Any],
        valid_from: datetime,
        tx_from: Optional[datetime] = None,
        entity_id: Optional[str] = None,
        valid_to: Optional[datetime] = None,
        tx_to: Optional[datetime] = None
    ) -> Entity:
        """Insert a new entity into the knowledge graph

        Args:
            entity_type: Type of entity (e.g., 'dci_job', 'jira_ticket')
            data: Entity data as a dictionary
            valid_from: When the fact became true in reality
            tx_from: When BOSS learned about it (defaults to now)
            entity_id: Optional entity ID (generated if not provided)
            valid_to: When the fact stopped being true (None if still valid)
            tx_to: When BOSS stopped believing it (None if current belief)

        Returns:
            The created Entity
        """
        if tx_from is None:
            tx_from = datetime.now()

        if entity_id is None:
            entity_id = f"{entity_type}-{uuid4().hex[:8]}"

        entity = Entity(
            id=entity_id,
            entity_type=entity_type,
            valid_from=valid_from,
            valid_to=valid_to,
            tx_from=tx_from,
            tx_to=tx_to,
            data=data
        )

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO entities (id, entity_type, valid_from, valid_to, tx_from, tx_to, data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            entity.id,
            entity.entity_type,
            entity.valid_from.isoformat(),
            entity.valid_to.isoformat() if entity.valid_to else None,
            entity.tx_from.isoformat(),
            entity.tx_to.isoformat() if entity.tx_to else None,
            json.dumps(entity.data)
        ))
        self.conn.commit()

        return entity

    def update_entity(
        self,
        entity_id: str,
        valid_to: Optional[datetime] = None,
        tx_to: Optional[datetime] = None
    ) -> Optional[Entity]:
        """Update an entity's temporal bounds

        This is used to close the temporal window (set valid_to or tx_to)
        For updating data, insert a new entity version instead.

        Args:
            entity_id: ID of the entity to update
            valid_to: Set when the fact stopped being true
            tx_to: Set when BOSS stopped believing it

        Returns:
            The updated Entity or None if not found
        """
        cursor = self.conn.cursor()

        # First get the current entity
        cursor.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
        row = cursor.fetchone()
        if not row:
            return None

        entity = Entity.from_row(row)

        # Update temporal bounds
        if valid_to is not None:
            entity.valid_to = valid_to
        if tx_to is not None:
            entity.tx_to = tx_to

        cursor.execute("""
            UPDATE entities
            SET valid_to = ?, tx_to = ?
            WHERE id = ?
        """, (
            entity.valid_to.isoformat() if entity.valid_to else None,
            entity.tx_to.isoformat() if entity.tx_to else None,
            entity_id
        ))
        self.conn.commit()

        return entity

    def insert_relationship(
        self,
        rel_type: str,
        source_id: str,
        target_id: str,
        valid_from: datetime,
        tx_from: Optional[datetime] = None,
        properties: Optional[dict[str, Any]] = None,
        rel_id: Optional[str] = None,
        valid_to: Optional[datetime] = None,
        tx_to: Optional[datetime] = None
    ) -> Relationship:
        """Insert a new relationship between entities

        Args:
            rel_type: Type of relationship
            source_id: Source entity ID
            target_id: Target entity ID
            valid_from: When the relationship became true
            tx_from: When BOSS learned about it (defaults to now)
            properties: Additional properties
            rel_id: Optional relationship ID (generated if not provided)
            valid_to: When the relationship stopped being true
            tx_to: When BOSS stopped believing it

        Returns:
            The created Relationship
        """
        if tx_from is None:
            tx_from = datetime.now()

        if rel_id is None:
            rel_id = f"rel-{uuid4().hex[:8]}"

        if properties is None:
            properties = {}

        relationship = Relationship(
            id=rel_id,
            rel_type=rel_type,
            source_id=source_id,
            target_id=target_id,
            valid_from=valid_from,
            valid_to=valid_to,
            tx_from=tx_from,
            tx_to=tx_to,
            properties=properties
        )

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO relationships
            (id, rel_type, source_id, target_id, valid_from, valid_to, tx_from, tx_to, properties)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            relationship.id,
            relationship.rel_type,
            relationship.source_id,
            relationship.target_id,
            relationship.valid_from.isoformat(),
            relationship.valid_to.isoformat() if relationship.valid_to else None,
            relationship.tx_from.isoformat(),
            relationship.tx_to.isoformat() if relationship.tx_to else None,
            json.dumps(relationship.properties)
        ))
        self.conn.commit()

        return relationship

    def query_as_of(
        self,
        tx_time: datetime,
        entity_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> list[Entity]:
        """Query entities as they were known at a specific transaction time

        This answers: "What did BOSS know at time X?"

        Args:
            tx_time: The transaction time to query
            entity_type: Optional filter by entity type
            limit: Optional limit on number of results

        Returns:
            List of entities that BOSS believed at tx_time
        """
        cursor = self.conn.cursor()

        query = """
            SELECT * FROM entities
            WHERE tx_from <= ? AND (tx_to IS NULL OR tx_to > ?)
        """
        params = [tx_time.isoformat(), tx_time.isoformat()]

        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)

        query += " ORDER BY tx_from DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        return [Entity.from_row(row) for row in cursor.fetchall()]

    def query_valid_at(
        self,
        valid_time: datetime,
        entity_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> list[Entity]:
        """Query entities that were valid at a specific time in reality

        This answers: "What was true at time X?"

        Args:
            valid_time: The valid time to query
            entity_type: Optional filter by entity type
            limit: Optional limit on number of results

        Returns:
            List of entities that were valid at valid_time
        """
        cursor = self.conn.cursor()

        query = """
            SELECT * FROM entities
            WHERE valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)
            AND tx_to IS NULL
        """
        params = [valid_time.isoformat(), valid_time.isoformat()]

        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)

        query += " ORDER BY valid_from DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        return [Entity.from_row(row) for row in cursor.fetchall()]

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID

        Args:
            entity_id: The entity ID

        Returns:
            The entity or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
        row = cursor.fetchone()
        return Entity.from_row(row) if row else None

    def get_related_entities(
        self,
        entity_id: str,
        rel_type: Optional[str] = None,
        direction: Literal["outgoing", "incoming", "both"] = "outgoing"
    ) -> list[tuple[Relationship, Entity]]:
        """Get entities related to this entity

        Args:
            entity_id: The entity ID
            rel_type: Optional filter by relationship type
            direction: Direction of traversal (outgoing, incoming, or both)

        Returns:
            List of (relationship, related_entity) tuples
        """
        cursor = self.conn.cursor()
        results = []

        if direction in ["outgoing", "both"]:
            query = """
                SELECT r.*, e.*
                FROM relationships r
                JOIN entities e ON r.target_id = e.id
                WHERE r.source_id = ? AND r.tx_to IS NULL AND e.tx_to IS NULL
            """
            params = [entity_id]

            if rel_type:
                query += " AND r.rel_type = ?"
                params.append(rel_type)

            cursor.execute(query, params)
            for row in cursor.fetchall():
                rel = Relationship.from_row(row[:9])
                entity = Entity.from_row(row[9:])
                results.append((rel, entity))

        if direction in ["incoming", "both"]:
            query = """
                SELECT r.*, e.*
                FROM relationships r
                JOIN entities e ON r.source_id = e.id
                WHERE r.target_id = ? AND r.tx_to IS NULL AND e.tx_to IS NULL
            """
            params = [entity_id]

            if rel_type:
                query += " AND r.rel_type = ?"
                params.append(rel_type)

            cursor.execute(query, params)
            for row in cursor.fetchall():
                rel = Relationship.from_row(row[:9])
                entity = Entity.from_row(row[9:])
                results.append((rel, entity))

        return results

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the knowledge graph

        Returns:
            Dictionary with counts and other statistics
        """
        cursor = self.conn.cursor()

        # Count entities by type
        cursor.execute("""
            SELECT entity_type, COUNT(*)
            FROM entities
            WHERE tx_to IS NULL
            GROUP BY entity_type
        """)
        entity_counts = dict(cursor.fetchall())

        # Total entities
        cursor.execute("SELECT COUNT(*) FROM entities WHERE tx_to IS NULL")
        total_entities = cursor.fetchone()[0]

        # Count relationships by type
        cursor.execute("""
            SELECT rel_type, COUNT(*)
            FROM relationships
            WHERE tx_to IS NULL
            GROUP BY rel_type
        """)
        relationship_counts = dict(cursor.fetchall())

        # Total relationships
        cursor.execute("SELECT COUNT(*) FROM relationships WHERE tx_to IS NULL")
        total_relationships = cursor.fetchone()[0]

        return {
            "db_path": self.db_path,
            "total_entities": total_entities,
            "entities_by_type": entity_counts,
            "total_relationships": total_relationships,
            "relationships_by_type": relationship_counts,
        }

    def close(self):
        """Close the database connection"""
        self.conn.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
