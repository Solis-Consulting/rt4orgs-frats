# Plan: Wire Sector → Vertical Inference

## Problem Statement

Cards are being uploaded with `sector` field (e.g., "Cultural Identity", "Faith-Based") but the system is not inferring the `vertical` field from `sector`. The `vertical` field is used for:
- Pitch template selection
- Vertical-specific field mappings
- Downstream classification and filtering

**Current State:**
- Cards have `sector` field set correctly
- `vertical` field is not being inferred from `sector`
- System stores cards but nothing downstream uses `sector` for vertical detection

## Root Cause Analysis

1. **`normalize_card()` preserves `vertical` if it exists** but doesn't infer it
2. **No mapping function exists** from `sector` → `vertical`
3. **`VERTICAL_TYPES` dictionary** has verticals like `"cultural"`, `"faith"`, `"frats"`, `"sports"` but no connection to sectors

## Solution Architecture

### Phase 1: Create Sector → Vertical Mapping

Create a deterministic mapping function that converts `sector` + `biz/org` → `vertical`:

```python
SECTOR_TO_VERTICAL_MAP = {
    # ORG sectors
    "Greek Life": "frats",
    "Faith-Based": "faith",
    "Cultural Identity": "cultural",
    "Honors Academic": "academic",
    "Professional Career": "government",  # Or create new vertical?
    "Club Sports": "sports",
    "Student Government": "government",
    "Arts Performance": "cultural",  # Or create new vertical?
    "Interest-Based": None,  # No vertical for unclassified
    
    # BIZ sectors (no direct vertical mapping - businesses are different)
    "Housing": None,  # Businesses don't use vertical system
    "Fitness": None,
    "Salons": None,
}
```

### Phase 2: Update `normalize_card()` to Infer Vertical

Modify `normalize_card()` to:
1. Check if `vertical` is already set (preserve it)
2. If not set, infer from `sector` using the mapping
3. Only set `vertical` for ORG cards (BIZ cards don't use vertical system)

### Phase 3: Handle Edge Cases

- **Interest-Based sector**: Don't set vertical (needs review)
- **BIZ cards**: Don't set vertical (business vertical system is separate)
- **Existing vertical**: Always preserve (user override)

## Implementation Steps

1. **Add `sector_to_vertical()` function** in `backend/cards.py`
   - Takes `sector` and `biz_org` as inputs
   - Returns `vertical` string or `None`
   - Handles all valid sectors

2. **Update `normalize_card()` function** in `backend/cards.py`
   - After determining `biz_org` and `sector`
   - If `vertical` not already set, call `sector_to_vertical()`
   - Only set for ORG cards

3. **Test with sample data**
   - Test "Cultural Identity" → "cultural"
   - Test "Faith-Based" → "faith"
   - Test "Greek Life" → "frats"
   - Test BIZ cards (should not get vertical)
   - Test Interest-Based (should not get vertical)

4. **Update existing cards** (optional migration script)
   - Script to backfill `vertical` for existing cards with `sector` but no `vertical`

## Files to Modify

1. `backend/cards.py`
   - Add `SECTOR_TO_VERTICAL_MAP` constant
   - Add `sector_to_vertical()` function
   - Update `normalize_card()` to infer vertical

2. `scripts/backfill_vertical_from_sector.py` (optional)
   - Migration script to update existing cards

## Key Design Decisions

- **Deterministic mapping**: No fuzzy inference, direct sector → vertical lookup
- **BIZ cards excluded**: Business vertical system is separate (if it exists)
- **Preserve existing vertical**: Never overwrite user-set vertical
- **Interest-Based = no vertical**: Unclassified cards don't get vertical

## Expected Outcomes

After implementation:
- Cards with `sector: "Cultural Identity"` will have `vertical: "cultural"`
- Cards with `sector: "Faith-Based"` will have `vertical: "faith"`
- Cards with `sector: "Greek Life"` will have `vertical: "frats"`
- Pitch templates will work correctly
- Vertical-based filtering will work

## Testing Checklist

- [ ] Upload card with `sector: "Cultural Identity"` → verify `vertical: "cultural"`
- [ ] Upload card with `sector: "Faith-Based"` → verify `vertical: "faith"`
- [ ] Upload card with `sector: "Greek Life"` → verify `vertical: "frats"`
- [ ] Upload BIZ card with `sector: "Salons"` → verify no vertical set
- [ ] Upload card with `sector: "Interest-Based"` → verify no vertical set
- [ ] Upload card with existing `vertical` → verify it's preserved
- [ ] Test pitch generation with inferred vertical

