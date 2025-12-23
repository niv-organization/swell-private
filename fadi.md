# AI Interaction Matching Heuristic
**Technical Brief for Engineering & Management**





## The Goal

**Input:** Daily AI interaction data per user
**Output:** Marked commits - specific commits we infer were involved in that AI interaction

---

## The Challenge

**Core Problem:** Most AI tools only provide **daily user-level interaction data** without specific commit identifiers.

**Example Scenario:**
```
Interaction data received:
- User: dev@company.com
- Date: 2024-12-09
- Lines written: 245 lines of code
```

**The Inference Problem:**
That developer made 12 commits that day across 5 different branches:
- `feature/api-redesign`: 3 commits, 230 lines total
- `feature/dashboard`: 2 commits, 180 lines total
- `fix/typo`: 1 commit, 2 lines
- `fix/import`: 2 commits, 8 lines total
- `fix/lint`: 4 commits, 15 lines total

**Question:** Which commits were AI-assisted? All of them? Just the large features? How do we decide?

**Data Granularity Levels:**

| Data Level | What's Provided | Approach |
|-----------|-----------------|----------|
| **Commit-level** | Exact commit SHA | ✅ Direct match (confidence: 1.0) |
| **Daily** | User + date + total lines | ⚠️ Ratio-based matching (confidence: dynamic ratio) |

**Main Challenge:** When only daily user-level data is available, we cannot determine which specific commits used AI. Our solution: mark ALL commits with a confidence ratio representing the proportion of AI-assisted work.

---

## Solution: Two-Tier Matching Strategy

```
┌─────────────────────────────────────────────┐
│ AI Interaction Data Received                │
│ Goal: Mark commits involved in interaction  │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
         ┌────────────────────┐
         │ Has commit_hash?   │  YES → [Tier 1: Direct Match]
         │                    │          → Mark specific commit
         └────────┬───────────┘          Confidence: 1.0 ✓
                  │ NO
                  ▼
         ┌────────────────────┐
         │ [Tier 2: Ratio-Based Match]
         │ 1. Fetch user commits (user + day)
         │ 2. Remove co-author commits
         │ 3. Calculate ratio:
         │    interaction_loc / user_total_loc
         │ 4. Mark ALL commits
         └────────────────────┘
         Confidence: ratio (dynamic) ✓
```

---

## Confidence Scores

Each tier has an associated confidence level indicating match quality:

| Tier | Criteria | Confidence | Reasoning |
|------|----------|------------|-----------|
| **1** | Commit hash provided | **1.0** | Tool explicitly told us exact commit |
| **2** | Daily user commits | **Dynamic ratio** | Calculated as: interaction_loc / user_total_loc (after co-author deduplication) |

**Tier 2 Confidence Calculation:**
- Ratio = (AI interaction lines - co-author lines) / (User total lines - co-author lines)
- Higher ratio = more of user's work involved AI = higher confidence
- Example: 500 AI lines / 1000 user lines = 0.5 confidence

---

## Tier 1: Direct Match

**When:** AI tool provides commit SHA

**Logic:**
```
If interaction has commit_hash:
  → Find commit with that SHA
  → Mark this specific commit ✓
```

**Example:**
```
Interaction: {
  user: "dev@company.com",
  date: "2024-12-09",
  commit_hash: "a1b2c3d4"
}

→ Find commit "a1b2c3d4"
→ Mark this commit ✓
```

---

## Tier 2: Ratio-Based Matching

**When:** AI tool provides user + date + LOC (no commit SHA)

**Core Logic:** Mark ALL user commits with confidence based on the ratio of AI interaction to user's total work.

**Steps:**
```
1. Fetch all user commits for that day
2. Remove co-author commits (already detected via co-author footprint)
3. Calculate adjusted interaction LOC = interaction_loc - co_author_loc
4. Calculate user total LOC = sum of all remaining commits
5. Calculate ratio = adjusted_interaction_loc / user_total_loc
6. If ratio > 0: Mark ALL remaining commits with confidence = ratio
```

**Example:**
```
Interaction: {
  user: "dev@company.com",
  date: "2024-12-09",
  lines_added: 400,
  lines_deleted: 100
}
Total interaction: 500 lines

User's commits that day:
  - Commit A: 200 lines, co_author: Cursor (dev_tool_id=26) ← Already marked via co-author
  - Commit B: 300 lines, no co-author
  - Commit C: 500 lines, no co-author

Step 1: Remove co-author commit
  Exclude Commit A (already detected)

Step 2: Adjust interaction LOC
  Adjusted interaction = 500 - 200 = 300 lines

Step 3: Calculate user total (remaining commits)
  User total = 300 + 500 = 800 lines

Step 4: Calculate ratio
  Ratio = 300 / 800 = 0.375

Step 5: Mark commits
  → Mark Commit B with confidence 0.375
  → Mark Commit C with confidence 0.375

Logic: The ratio (0.375 = 37.5%) indicates that roughly 37.5% of the user's
       work that day involved AI assistance. We mark all commits with this
       confidence level, representing the proportion of AI-assisted work.
```

**Key Benefits:**
- **Simple:** No complex branch grouping or filtering
- **Fair:** All commits treated equally - reflects uncertainty about which specific commits used AI
- **Transparent:** Confidence score directly represents AI usage proportion
- **Co-author aware:** Avoids double-counting commits already detected via co-author

---

## Pseudo Code: Ratio-Based Algorithm

```python
def match_commits_to_interaction(user_commits, interaction):
    """
    Ratio-based matching algorithm for Tier 2.

    Args:
        user_commits: List of all user's commits from that day
        interaction: AI interaction data with lines_added, lines_deleted, dev_tool_id

    Returns:
        List of commits to mark with their confidence scores
    """
    interaction_total = interaction.lines_added + interaction.lines_deleted

    # Step 1: Remove co-author commits
    coauthor_total_lines = 0
    remaining_commits = []

    for commit in user_commits:
        # Check if commit has co-author with same dev_tool_id
        if has_coauthor(commit, interaction.dev_tool_id):
            coauthor_total_lines += commit.total_lines
            # Skip this commit (already detected via co-author)
        else:
            remaining_commits.append(commit)

    # Step 2: Adjust interaction total
    adjusted_interaction_total = max(0, interaction_total - coauthor_total_lines)

    # Step 3: Calculate user total from remaining commits
    user_total_lines = sum(c.total_lines for c in remaining_commits)

    # Step 4: Calculate confidence ratio
    if user_total_lines == 0:
        return []  # No commits to mark

    confidence_ratio = adjusted_interaction_total / user_total_lines

    # Step 5: Mark all remaining commits if ratio > 0
    if confidence_ratio > 0:
        return [(commit, confidence_ratio) for commit in remaining_commits]
    else:
        return []
```

---

## Current Implementation Status

### ✅ Implemented
- Tier 1: Direct commit hash matching with 1.0 confidence

### 🚧 Needs Implementation
- **Tier 2:** Ratio-based matching with dynamic confidence
  - Fetch user commits by date
  - Co-author deduplication
  - Ratio calculation
  - Mark all commits with ratio as confidence

---

## Summary for Executives

**Goal:** Match daily AI interaction data to specific commits

**Two-Tier Strategy:**
1. **Tier 1 (confidence: 1.0):** Direct match when tool provides commit SHA
2. **Tier 2 (confidence: dynamic ratio):** Ratio-based matching for daily user data

**Key Algorithm: Ratio-Based Matching**
- Fetch all user commits for that day
- Remove commits already detected via co-author
- Calculate ratio = AI_interaction_lines / user_total_lines
- Mark ALL remaining commits with confidence = ratio

**Key Benefits:**
- **Simple & transparent:** Confidence directly represents AI usage proportion
- **Fair:** All commits treated equally when we don't know which specific ones used AI
- **Avoids double-counting:** Co-author commits excluded from ratio calculation

---

## Data Algorithm Flow

### Step 1: Input Data
```
Required:
  - user (email)
  - date (daily)
  - AI interaction lines (lines_added, lines_deleted)
  - dev_tool_id
  - Optional: commit_hash (for Tier 1 direct match)
```

### Step 2: Resolve Contributor
```
user email → contributor_id
(Use ContributorResolver to map email to internal contributor ID)
```

### Step 3: Fetch Commits
```
Query commits by:
  - contributor_id
  - date (daily)

Returns list of commits for that user on that day
```

### Step 4: Extract Per-Commit Data

**For each commit, extract:**

**a) Core identifiers**
```
commit.commit_id
commit.sha (for Tier 1 matching)
commit.timestamp
```

**b) Branch information**
```
commit.branch_id
commit.branch_name
```

**c) Code lines** (for ratio calculation)
```json
{
  "commit.activity.total.count": 245
}
```
Extract total lines of code for ratio calculation

**d) Co-authors** (for deduplication)
```
commit.co_authors → extract dev_tool_ids
```

### Step 5: Co-Author Deduplication

```
For each commit in commits:
  If commit has co_author where co_author.dev_tool_id == interaction.dev_tool_id:
    - Remove commit from candidates
    - Subtract commit.lines from interaction_total

Result: remaining_commits, adjusted_interaction_total
```

### Step 6: Calculate Ratio

```
user_total_lines = sum(c.total_lines for c in remaining_commits)
confidence_ratio = adjusted_interaction_total / user_total_lines

If ratio > 0:
  Mark all remaining_commits with confidence = ratio
```

### Step 7: Mark Commits

```
For each commit in remaining_commits (if ratio > 0):
  Create AIFootprintRecord:
    - commit_id
    - dev_tool_id
    - confidence_score = ratio
    - timestamp
    - type: 'ai_interaction'
```

---

## Data Requirements Summary

**From AI Tool API:**
- user (email)
- date
- lines_added
- lines_deleted
- dev_tool_id
- Optional: commit_hash (for Tier 1 direct match)

**From LinearB Database (per commit):**
- commit_id
- sha (for Tier 1 matching)
- timestamp
- contributor_id (for fetching user commits)
- branch_id, branch_name
- commit.activity.total.count (code lines for ratio calculation)
- co_authors with dev_tool_ids (for deduplication)
