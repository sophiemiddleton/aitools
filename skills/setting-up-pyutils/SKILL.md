---
name: setting-up-pyutils
description: Install and configure the Mu2e pyutils library, verify the installation, and create your first working processor. Use when you need to set up pyutils for the first time or troubleshoot installation issues.
compatibility: Requires mu2einit, Python 3.7+, git access to github.com/Mu2e/pyutils
metadata:
  version: "1.0.0"
  last-updated: "2026-04-27"
---

# Setting Up Pyutils

## Overview

Use this skill to install the Mu2e pyutils library and verify your setup is working. After completing this skill, you'll have a functional pyutils environment and a basic first processor running.

Key outcomes:
- Clone and install pyutils from GitHub
- Set up the Mu2e development environment
- Verify imports and dependencies
- Understand processor class structure and lifecycle
- Run your first working processor example

---

## Setup and Installation

### Clone the Repository

Start by cloning the pyutils repository from GitHub:

```bash
cd ~/src  # or your preferred development directory
git clone https://github.com/Mu2e/pyutils.git
cd pyutils
```

### Install Dependencies

Install pyutils and its dependencies in development mode:

```bash
# Option 1: Using pip (recommended for development)
pip install -e .

# Option 2: Using setup.py directly
python setup.py develop

# Option 3: Using conda (if conda environment is preferred)
conda install -c conda-forge root pandas numpy scipy matplotlib
pip install -e .
```

### Environment Setup

The preferred way to set up the environment for working with pyutils is using the standard Mu2e python environment:

```bash
mu2einit
pyenv ana
```

This ensures ROOT, art modules, and other Mu2e dependencies are available alongside pyutils.

### Verify Installation

Test that pyutils is properly installed:

```bash
python -c "import pyutils; print(pyutils.__version__)"
```

Quick import test to verify core modules load:

```python
from pyutils.processor import Processor
from pyutils.pyprocess import Skeleton
from pyutils.pylogger import Logger
print("Pyutils imported successfully!")
```

If all imports succeed, your installation is ready.

---

## Understanding the Processor Framework

### The Skeleton Base Class

All Mu2e processors inherit from the `Skeleton` class, which provides:

- **Parallel file processing**: Automatic multithreading/multiprocessing across input files
- **Lifecycle management**: Orchestrates `begin_job()` → `process_file()` → `end_job()`
- **Result aggregation**: Combines results from multiple files via `postprocess()`
- **Remote file support**: Built-in mdh integration for fetching files from dCache/tape
- **Logging and configuration**: Verbosity control, file location management

### Processor Lifecycle

Every processor follows this pattern:

```
1. begin_job()        ← Called once at start (setup)
    ↓
2. process_file()     ← Called for each input file (can run in parallel)
    ↓ (repeats for each file)
3. postprocess()      ← Called once after all files (combine results)
    ↓
4. end_job()          ← Called once at end (finalize)
```

---

## Your First Processor

Here's a minimal working processor that reads files and counts events:

```python
from pyutils.pyprocess import Skeleton, Processor
from pyutils.pylogger import Logger

class FirstProcessor(Skeleton):
    """Minimal processor example - counts events in ROOT files."""
    
    def __init__(self, file_list_path, jobs=1, location='disk'):
        """Initialize processor.
        
        Args:
            file_list_path: Path to text file listing ROOT files
            jobs: Number of parallel workers
            location: 'local' or 'disk' (for remote mdh access)
        """
        super().__init__()
        
        self.file_list_path = file_list_path
        self.tree_path = "EventNtuple/ntuple"
        self.use_remote = (location != "local")
        self.location = location
        self.max_workers = jobs
        self.verbosity = 1
        self.use_processes = True
        
        # Define minimal branches to read
        self.branches = {
            "evt": ["run", "subrun", "event"],
            "trk": ["trk.pdg", "trk.status"]
        }
        
        self.logger = Logger(print_prefix="[FirstProcessor]", verbosity=1)
    
    def begin_job(self):
        """Set up counters at start of analysis."""
        self.logger.log("Beginning job", "info")
        self.total_events = 0
        self.total_tracks = 0
    
    def process_file(self, file_name):
        """Process single file - extract events and tracks."""
        try:
            # Create processor to read raw data
            processor = Processor(
                use_remote=self.use_remote,
                location=self.location,
                verbosity=0
            )
            
            # Load data from ROOT file
            data = processor.process_data(
                file_name=file_name,
                branches=self.branches
            )
            
            # Count events and tracks in this file
            n_events = len(data)
            
            import awkward as ak
            n_tracks = ak.sum(ak.num(data["trk"], axis=-1))
            
            self.logger.log(
                f"File: {n_events} events, {n_tracks} tracks",
                "info"
            )
            
            return {
                "events": n_events,
                "tracks": int(n_tracks)
            }
        
        except Exception as e:
            self.logger.log(f"Error processing {file_name}: {e}", "error")
            return None
    
    def postprocess(self, results):
        """Combine results from all files."""
        if not results:
            return None
        
        total_events = sum(r["events"] for r in results if r is not None)
        total_tracks = sum(r["tracks"] for r in results if r is not None)
        
        self.logger.log(
            f"Total: {total_events} events, {total_tracks} tracks",
            "info"
        )
        
        return {
            "total_events": total_events,
            "total_tracks": total_tracks
        }
    
    def end_job(self):
        """Finalize analysis."""
        self.logger.log("Job complete", "success")

# Usage
if __name__ == "__main__":
    # Create processor
    processor = FirstProcessor("my_file_list.txt", jobs=1, location='disk')
    
    # Run the entire pipeline
    results = processor.execute()
    
    print(f"\nFinal Results:")
    print(f"  Events: {results['total_events']}")
    print(f"  Tracks: {results['total_tracks']}")
```

### Running Your First Processor

**Create a file list** (`my_file_list.txt`):
```
/path/to/file1.root
/path/to/file2.root
/path/to/file3.root
```

**Run the processor:**
```bash
python your_processor.py
```

You should see output showing event and track counts from each file.

---

## Key Components Explained

### 1. Initialization (`__init__`)

Set up processor configuration:

```python
def __init__(self, file_list_path, jobs=1, location='disk'):
    super().__init__()
    
    # Required: where to find input files and ROOT tree
    self.file_list_path = file_list_path
    self.tree_path = "EventNtuple/ntuple"
    
    # Parallelization
    self.max_workers = jobs          # Number of parallel workers
    self.use_processes = True        # Use processes (not threads)
    
    # Remote file access (mdh integration)
    self.use_remote = (location != "local")
    self.location = location         # 'local' or 'disk'
    
    # I/O
    self.verbosity = 1               # 0=quiet, 1=normal, 2=verbose
    
    # Define branches to read (nested hierarchy)
    self.branches = {
        "evt": ["run", "subrun", "event"],
        "trk": ["trk.pdg", "trk.status"]
    }
```

### 2. begin_job() - One-Time Setup

Called once at the start. Initialize shared resources:

```python
def begin_job(self):
    """Called once at job start."""
    self.logger.log("Setting up analysis", "info")
    self.event_count = 0
    self.errors = 0
```

### 3. process_file() - Per-File Processing

Called for each input file (runs in parallel). Extract data and return results:

```python
def process_file(self, file_name):
    """Called for each file (can run in parallel workers)."""
    try:
        processor = Processor(use_remote=self.use_remote, location=self.location)
        data = processor.process_data(file_name=file_name, branches=self.branches)
        
        # Do analysis
        result = analyze(data)
        
        return result
    except Exception as e:
        self.logger.log(f"Error in {file_name}: {e}", "error")
        return None
```

**Important**: Each worker process runs independently. Return a dict with results that will be combined by `postprocess()`.

### 4. postprocess() - Combine All Results

Called once after all files are processed. Combine partial results:

```python
def postprocess(self, results):
    """Combine results from all parallel workers."""
    # results is a list of dicts returned by process_file()
    combined = combine_all_results(results)
    return combined
```

### 5. end_job() - Finalization

Called once at the end. Save outputs and print summaries:

```python
def end_job(self):
    """Called once at job end."""
    self.logger.log("Analysis complete", "success")
    self.save_outputs()
```

### 6. execute() - Main Entry Point

Runs the entire pipeline:

```python
processor = MyProcessor("file_list.txt", jobs=4)
results = processor.execute()  # Runs begin_job → process_file (×N) → postprocess → end_job
```

---

## Creating Your First File List

To run a processor, you need a text file listing ROOT files. One file per line:

**my_file_list.txt:**
```
/exp/mu2e/data/tdr/rec/20200101/00/dts.owner.dataset-a.root
/exp/mu2e/data/tdr/rec/20200101/01/dts.owner.dataset-b.root
/exp/mu2e/data/tdr/rec/20200101/02/dts.owner.dataset-c.root
```

Generate from file search:
```bash
# Using metacat (see coding-with-metacat skill)
metacat query-files "experiment:mu2e AND dataset_name:my-dataset" --format=plain > my_file_list.txt

# Or using SAM
sam_getFileLocations "dh experiment=mu2e and dataset_name=my-dataset" > my_file_list.txt
```

---

## Common Configuration Options

| Parameter | Purpose | Default | Notes |
|-----------|---------|---------|-------|
| `max_workers` | Parallel file processing | 1 | Set to 4-8 for typical usage |
| `use_processes` | Process vs thread parallelism | True | Recommended for data processing |
| `tree_path` | Path to ROOT tree in file | "EventNtuple/ntuple" | Depends on file format |
| `use_remote` | Fetch from dCache/tape | False | Set True for remote files |
| `location` | File storage location | 'disk' | 'local', 'disk', 'tape' |
| `verbosity` | Logging verbosity | 1 | 0=quiet, 1=normal, 2=verbose |

---

## Troubleshooting

### Issue: ImportError: No module named pyutils

**Problem:** Python can't find the pyutils package

**Solution:**
```bash
# Verify installation
python -c "import pyutils; print(pyutils.__file__)"

# If not found, reinstall
cd ~/src/pyutils
pip install -e .

# Verify again
python -c "from pyutils.pyprocess import Skeleton; print('OK')"
```


### Issue: FileNotFoundError: No such file or directory

**Problem:** File list or input files not found

**Solution:**
```bash
# Check file list exists and has correct paths
cat my_file_list.txt

# Verify each file exists
while read line; do
    if [ ! -f "$line" ]; then
        echo "Missing: $line"
    fi
done < my_file_list.txt

# If using remote files, check mdh access
mdh --help
mdh locate <filename>
```

### Issue: Processor hangs or runs very slowly

**Problem:** Parallel processing not configured correctly

**Solution:**
```python
# Start with single worker for debugging
processor = MyProcessor("file_list.txt", jobs=1)

# Check available cores
import multiprocessing
print(multiprocessing.cpu_count())

# Then scale up appropriately
processor = MyProcessor("file_list.txt", jobs=4)  # Use 4 of 8 cores
```

### Issue: Empty or incomplete results

**Problem:** Files processed but no data returned

**Solution:**
```python
# Add debug logging in process_file()
def process_file(self, file_name):
    try:
        data = processor.process_data(file_name, self.branches)
        n_events = len(data)
        self.logger.log(f"{file_name}: {n_events} events", "debug")
        
        if n_events == 0:
            self.logger.log(f"WARNING: No events in {file_name}", "warning")
        
        return analyze(data)
    except Exception as e:
        self.logger.log(f"ERROR {file_name}: {e}", "error")
        import traceback
        self.logger.log(traceback.format_exc(), "error")
        return None
```

### Issue: AttributeError when accessing branches

**Problem:** Requested branch doesn't exist in file

**Solution:**
```bash
# Inspect available branches in a ROOT file
python << 'EOF'
import uproot

with uproot.open("your_file.root") as f:
    tree = f["EventNtuple/ntuple"]
    print("Available branches:")
    for key in tree.keys():
        print(f"  {key}")
EOF

# Then update self.branches to match available branches
```

---

## Next Steps

Once your processor is running:

1. **Verify you can read data** - Your first processor should count events successfully
2. **Check file sizes** - Ensure files are being read completely
3. **Move on to physics analysis** - See the `analyzing-with-pyutils` skill to learn how to:
   - Access EventNtuple branches and fields
   - Define physics cuts with CutManager
   - Fill histograms and analysis plots
   - Process detector data with physics-aware operations

---

## Key Classes Reference

### Skeleton
```python
from pyutils.pyprocess import Skeleton

class MyProcessor(Skeleton):
    def __init__(self, file_list_path, jobs=1, location='disk'):
        super().__init__()
        # Configure via self.* attributes
```

### Processor
```python
from pyutils.pyprocess import Processor

processor = Processor(use_remote=True, location='disk', verbosity=0)
data = processor.process_data(file_name="file.root", branches={"evt": ["run"]})
```

### Logger
```python
from pyutils.pylogger import Logger

logger = Logger(print_prefix="[MyJob]", verbosity=1)
logger.log("Message text", "info")  # or "debug", "warning", "error", "success"
```

---

## Resources

- **PyUtils Repository**: https://github.com/Mu2e/pyutils
- **Mu2e Offline Wiki**: https://mu2ewiki.fnal.gov/wiki/Main_Page
- **Computing Help**: https://mu2ewiki.fnal.gov/wiki/Computing

---

## See Also

- `analyzing-with-pyutils` - Physics analysis workflows (cuts, histograms, data structures)
- `coding-with-metacat` - Finding and querying Mu2e ROOT files
- `finding-data-sam` - Alternative data discovery method
