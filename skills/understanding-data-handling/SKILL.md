---
name: understanding-data-handling
description: Overview of Mu2e data handling architecture, file naming conventions, dCache storage, and SAM-to-metacat transition. Use when understanding data organization, storage locations, or choosing between SAM and metacat tools.
compatibility: Requires mu2einit, kerberos authentication
metadata:
  version: "1.0.0"
  last-updated: "2026-02-13"
---

# Mu2e Data Handling - Overview

## Architecture and Transition

Mu2e data handling is currently in a **extended transition** from legacy to modern systems.

**Current state (~90% of workflow):**
- **Primary tool**: SAM (Sequential Access Management)
  - Monolithic file catalog + location database
  - Works well but increasingly difficult to scale
  - Still the standard for most production and user workflows
  - Still the primary way datasets are defined and accessed

**New tools (gradual migration):**
- **File catalog**: metacat (Fermilab metadata catalog)
- **Location database**: Rucio (ATLAS-proven data management system)
- **Mu2e customization layer**: mdh (Python convenience tool for Mu2e)
- **Conversion process**: Automated system converts SAM records → metacat
  - **Important limitation**: Conversion is one-way and not complete
  - If a file is retired in SAM, that retirement may NOT be reflected in metacat
  - The transition was expected to be brief; the incomplete sync was acceptable during that period
  - The transition has lasted longer than expected, so manual oversight may be needed

**Physical storage (unchanged):**
- dCache (distributed disk/tape system)

**Guidance:**
- New users should learn metacat/Rucio/mdh workflows
- Existing SAM-based workflows continue to work
- If you're thinking in SAM terms, that's fine — just know the mapping to new tools
- Over time, metacat/Rucio will become the standard

## Key Concepts

### Storage: dCache

**dCache** is a distributed storage system that presents many disks across dozens of servers as a single logical filesystem. All registered data files live in dCache under `/pnfs/mu2e/`.

**Five flavors (areas):**

1. **tape** - Tape-backed persistent storage
   - Primary location for production and registered datasets
   - Files are written to disk, then migrated to tape automatically
   - Regular use of these files requires prestaging from tape
   - Path: `/pnfs/mu2e/tape/`
   - Physically: tape, with disk cache

2. **persistent** - Disk-only permanent storage
   - Files stay until explicitly deleted
   - No automatic purging
   - Use for important, long-term datasets
   - Path: `/pnfs/mu2e/persistent/`

3. **scratch** - Temporary disk space with automatic purging
   - Files deleted by LRU (least-recently-used) after ~1-2 weeks
   - For temporary outputs, user experiments, testing
   - Path: `/pnfs/mu2e/scratch/users/$USER/`
   - NOT suitable as final production output

4. **resilient** - Replicated disk storage
   - Files copied to ~20 different disk nodes
   - Load-balanced for simultaneous reads by many grid jobs
   - Like scratch, no guaranteed lifetime
   - Not commonly used; RCDS (rapid code distribution) is preferred instead

5. **stashCache** - For large files needed by many grid jobs
   - Single file distributed to many compute nodes
   - Example: 5 GB library of templates
   - Alternative to CVMFS for large shared data

**Key dCache constraints:**
- Files cannot be modified or overwritten (delete and recreate instead)
- Interactive access via `/pnfs/` is slow due to database latency
- Builds and analysis should NOT use dCache directly
- Data transfer tools should be used for parallel/grid access (ifdh, xrootd, gfal, etc.)

### File Naming and Datasets

**All registered files follow a strict six-field naming convention:**

```
data_tier.owner.description.configuration.sequencer.file_format
```

Example:
```
sim.mu2e.beam_g4s1_dsregion.0429a.123456_12345678.art
```

**Fields explained:**

- **data_tier** - Type of content (sim, dig, mcs, raw, rec, nts, etc.)
- **owner** - `mu2e` for collaboration files, or username for personal files
- **description** - What this dataset represents (max ~20 chars, mnemonic)
- **configuration** - Configuration details, variants, tags (max ~20 chars)
- **sequencer** - Uniquifier; typically `RUNNUM_SUBRUNNUM` for art files
- **file_format** - `.art`, `.root`, `.fcl`, `.log`, etc.

**Datasets** are logical groupings formed by removing the sequencer:

```
data_tier.owner.description.configuration.file_format
```

Example (same as file above, minus sequencer):
```
sim.mu2e.beam_g4s1_dsregion.0429a.art
```

All files in a dataset are "more of the same" — same physics, same configuration, just different run/subrun numbers. Datasets are the unit users typically work with.

**Data identifiers (DIDs):**

Files and datasets can be referred to with namespace prefixes:

```
mu2e:sim.mu2e.beam_g4s1_dsregion.0429a.123456_12345678.art       # Full file DID
mu2e:sim.mu2e.beam_g4s1_dsregion.0429a.art                        # Dataset DID
USERNAME:sim.USERNAME.myanalysis.v1.001000_000001.art            # User file DID
```

### File Catalog: metacat

**metacat** is the file catalog database. It stores metadata about files:
- File names and paths
- Creation time, size, checksums
- Data tier, owner, configuration, run/subrun info
- Custom metadata fields

**Common operations:**

```bash
# List all datasets (collaboration)
metacat dataset list mu2e:*

# List your datasets
metacat dataset list $USER:*

# Query files in a dataset
metacat query files from mu2e:sim.mu2e.beam_g4s1_dsregion.0429a.art

# Show metadata for a file
metacat file show mu2e:sim.mu2e.beam_g4s1_dsregion.0429a.123456_12345678.art
```

### Location Database: Rucio

**Rucio** tracks where files physically live (which dCache location, tape status, replicas).

It knows:
- Is this file on disk, tape, or both?
- Where exactly in dCache is it? (tape area, persistent area, scratch)
- Are there replicas at other sites?

Rucio enforces strict immutability: once a file's checksum and size are registered, they cannot change. This prevents accidental overwrites and data corruption, but means new versions require new filenames.

### Mu2e Convenience Layer: mdh

**mdh** is a Python tool that wraps metacat and Rucio operations for Mu2e-specific workflows. It:
- Automates path construction to dCache files
- Handles prestaging files from tape
- Simplifies metadata creation and file declaration
- Manages uploads with proper policies
- Provides convenient command-line interface

**Common mdh operations:**

```bash
# Print the dCache path to a file (for on-site access)
mdh print-url -s path -l tape FILENAME

# Generate ROOT URLs for files (for art jobs)
metacat query files from DATASET | mdh print-url -l tape -s root -

# Check if dataset is on disk, tape, or both
mdh query-dcache -o -v DATASET

# Request files be staged from tape to disk
mdh prestage-files DATASET

# Create metadata for a file
mdh create-metadata FILENAME > FILENAME.json

# Declare files to metacat
mdh declare-file FILENAME.json

# Upload file to dCache
mdh copy-file -s -l scratch FILENAME
```

## Workflow Overview

### Finding and Using Existing Data

1. **Identify dataset** (via monitor page or search metacat)
   ```bash
   metacat dataset list mu2e:*
   ```

2. **Check file status** (on disk, tape, or both)
   ```bash
   mdh query-dcache -o -v mu2e:mcs.mu2e.example.config.art
   ```

3. **If on tape, prestage files** (copy from tape to disk cache)
   ```bash
   mdh prestage-files mu2e:mcs.mu2e.example.config.art
   ```

4. **Get file URLs** (for use in art jobs or analysis)
   ```bash
   metacat query files from mu2e:mcs.mu2e.example.config.art \
     | mdh print-url -l tape -s root -
   ```

5. **Use in art job** (URLs are passed to art's FileListProducer)

### Creating and Sharing Personal Data

1. **Create file** with proper naming convention
   ```
   sim.USERNAME.myanalysis.v1.001000_000001.art
   ```

2. **Create metadata**
   ```bash
   mdh create-metadata FILENAME > FILENAME.json
   ```

3. **Declare to metacat**
   ```bash
   mdh declare-file FILENAME.json
   ```

4. **Copy to dCache** (scratch for temporary, persistent for long-term)
   ```bash
   mdh copy-file -s -l scratch FILENAME
   ```

5. **Optional: Register with Rucio** (for formal sharing/sustainability)
   - Makes file discoverable across the collaboration
   - Enables Rucio-managed transfers and replication
   - Only do this for files you intend to share long-term

## Practical Notes

### Authentication

Mu2e services (metacat, Data Dispatcher / ddisp, SAM) share a common auth chain
built on Kerberos → OAuth token. The same flow applies to all of them.

#### Auth chain overview

```
Kerberos identity  →  OAuth token (getToken)  →  service login
```

#### User account setup (interactive)

```bash
mu2einit           # Set up Mu2e environment (sets service URLs, loads modules)
getToken           # Exchange Kerberos ticket for an OAuth token (~2h validity)
muse setup ops     # Load metacat, ddisp, mdh and related tools into path

# Authenticate each service using the OAuth token:
metacat auth login -m token $USER
ddisp login -m token $USER
```

- `getToken` derives the OAuth token from the active Kerberos ticket (`kinit`).
- Run `getToken` again at any time to refresh; no need to re-login to services.
- The service auth sessions last as long as the OAuth token (~2h).
- `kinit` is only needed if the Kerberos ticket itself has expired.

#### Production / automated accounts (e.g. mu2epro)

- Cron jobs automatically refresh the OAuth token and re-authenticate to
  metacat and ddisp; no manual steps are needed.
- The same `getToken` / `metacat auth login` / `ddisp login` commands underlie
  the cron workflow.

#### Quick reference

```bash
kinit                              # Renew Kerberos ticket if expired
getToken                           # (Re)issue OAuth token from Kerberos
metacat auth login -m token $USER  # Authenticate CLI / Python API to metacat
ddisp   login -m token $USER       # Authenticate CLI / Python API to ddisp
```

### For AI Assistants

When helping with data handling:

1. **SAM is still primary**: ~90% of current workflows still use SAM
   - If a user mentions SAM, engage with that — don't dismiss it
   - SAM and metacat/Rucio often work in parallel
   - Conversion process exists but is one-way only (retirements may not sync)

2. **Gently guide toward new tools**:
   - When discussing new workflows or long-term practices, point to metacat/mdh
   - For existing SAM setup, explain how SAM maps to metacat concepts
   - Don't force migration; let users choose their pace

3. **File naming**: Strictly six-field format required for registered files
4. **dCache flavors**: tape (production), persistent (permanent), scratch (temporary)
5. **Prestaging**: Files on tape-backed dCache must be prestaged before use
6. **mdh is user-facing**: Commands like `mdh prestage-files`, `mdh print-url` are how users interact
7. **Datasets, not files**: Users typically work with datasets, not individual files

### SAM-to-Metacat Mapping (for users thinking in SAM terms)

| SAM Concept | Metacat Equivalent | Notes |
|-------------|-------------------|-------|
| File in SAM | File in metacat | Same naming convention, same metadata |
| SAM dataset definition | Dataset in metacat | Logical grouping of files |
| samweb list-files | metacat query files | Different syntax, same result |
| samweb get-metadata | metacat file show | Access file metadata |
| SAM file retirement | Metacat file withdrawal | **May not be in sync** |
| File location query | Rucio + mdh | More powerful, multi-location aware |

### Common Commands Summary

```bash
# Setup
mu2einit
muse setup ops          # Brings in metacat, Rucio, mdh tools

# Find data
metacat dataset list mu2e:*
metacat query files from DATASET

# Check status
mdh query-dcache -o -v DATASET

# Get URLs
metacat query files from DATASET | mdh print-url -l tape -s root -

# Prestage
mdh prestage-files DATASET

# Create personal files
mdh create-metadata FILE.art > FILE.art.json
mdh declare-file FILE.art.json
mdh copy-file -s -l scratch FILE.art
```

## Related Topics (Future Skills)

Individual tools will have detailed references:
- **Metacat** - File catalog queries, metadata manipulation
- **Rucio** - File locations, data transfer, replication
- **dCache** - Storage details, access protocols, prestaging
- **mdh** - Full command reference and workflows

---

**Last updated**: 2026-02-12  
**Note**: This is an overview. For detailed tool documentation, see individual skill files.

