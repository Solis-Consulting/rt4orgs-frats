"""
Query engine for converting where clauses to SQL JSONB queries.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
import json


def build_query_filter(where: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """
    Convert where clause dict to SQL WHERE clause and parameters.
    
    Supports:
    - Direct field equality: {"fraternity": "SNU"} -> card_data->>'fraternity' = %s
    - Nested field access: {"metadata.insta": "value"} -> card_data->'metadata'->>'insta' = %s
    - Array membership: {"tags": ["rush"]} -> card_data->'tags' @> %s::jsonb
    - IN clause: {"sales_state": ["interested", "qualified"]} -> sales_state IN (%s, %s)
    - Array length: {"members.length": {"$gt": 5}} -> jsonb_array_length(card_data->'members') > %s
    
    Returns (where_clause, params_list).
    """
    conditions = []
    params = []
    
    for key, value in where.items():
        if key == "sales_state":
            # Handle sales_state (top-level column, not in card_data)
            if isinstance(value, list):
                placeholders = ",".join(["%s"] * len(value))
                conditions.append(f"sales_state IN ({placeholders})")
                params.extend(value)
            else:
                conditions.append("sales_state = %s")
                params.append(value)
        
        elif key == "type":
            # Handle type (top-level column)
            if isinstance(value, list):
                placeholders = ",".join(["%s"] * len(value))
                conditions.append(f"type IN ({placeholders})")
                params.extend(value)
            else:
                conditions.append("type = %s")
                params.append(value)
        
        elif key == "owner":
            # Handle owner (top-level column)
            if isinstance(value, list):
                placeholders = ",".join(["%s"] * len(value))
                conditions.append(f"owner IN ({placeholders})")
                params.extend(value)
            else:
                conditions.append("owner = %s")
                params.append(value)
        
        elif key.endswith(".length"):
            # Array length query: {"members.length": {"$gt": 5}}
            field = key[:-7]  # Remove ".length"
            if isinstance(value, dict):
                for op, op_value in value.items():
                    if op == "$gt":
                        conditions.append(f"jsonb_array_length(card_data->'{field}') > %s")
                        params.append(op_value)
                    elif op == "$gte":
                        conditions.append(f"jsonb_array_length(card_data->'{field}') >= %s")
                        params.append(op_value)
                    elif op == "$lt":
                        conditions.append(f"jsonb_array_length(card_data->'{field}') < %s")
                        params.append(op_value)
                    elif op == "$lte":
                        conditions.append(f"jsonb_array_length(card_data->'{field}') <= %s")
                        params.append(op_value)
                    elif op == "$eq":
                        conditions.append(f"jsonb_array_length(card_data->'{field}') = %s")
                        params.append(op_value)
        
        elif "." in key:
            # Nested field access: {"metadata.insta": "value"}
            parts = key.split(".")
            json_path = "->".join([f"'{p}'" for p in parts[:-1]])
            field = parts[-1]
            conditions.append(f"card_data{json_path}->>'{field}' = %s")
            params.append(value)
        
        elif isinstance(value, list):
            # Array membership: {"tags": ["rush"]} -> @> operator
            conditions.append(f"card_data->'{key}' @> %s::jsonb")
            params.append(json.dumps(value))
        
        else:
            # Direct field equality: {"fraternity": "SNU"}
            conditions.append(f"card_data->>'{key}' = %s")
            params.append(value)
    
    if conditions:
        where_clause = " AND ".join(conditions)
        return where_clause, params
    
    return "", []


def build_list_query(
    where: Optional[Dict[str, Any]] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None
) -> Tuple[str, List[Any]]:
    """
    Build complete SELECT query with WHERE, LIMIT, OFFSET.
    Returns (query, params).
    """
    # Check if upload_batch_id column exists (may not exist in old schema)
    # For now, we'll try to select it and handle gracefully if it doesn't exist
    query = """
        SELECT id, type, card_data, sales_state, owner, created_at, updated_at, 
               COALESCE(upload_batch_id, NULL) as upload_batch_id
        FROM cards
    """
    
    params = []
    
    if where:
        where_clause, where_params = build_query_filter(where)
        if where_clause:
            query += f" WHERE {where_clause}"
            params.extend(where_params)
    
    query += " ORDER BY updated_at DESC"
    
    if limit:
        query += " LIMIT %s"
        params.append(limit)
    
    if offset:
        query += " OFFSET %s"
        params.append(offset)
    
    return query, params

