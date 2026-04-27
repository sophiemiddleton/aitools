---
name: analyzing-with-pyutils
description: Perform physics analysis with Mu2e pyutils - extract detector data, define physics cuts with CutManager, fill histograms, and build complete analysis pipelines. Use when developing analysis workflows, selecting physics events, or calculating detector quantities.
compatibility: Requires setting-up-pyutils skill completed, pyutils installed, Python 3.7+
metadata:
  version: "1.0.0"
  last-updated: "2026-04-27"
---

# Analyzing with Pyutils

## Overview

Use this skill to develop physics analysis workflows with pyutils. This assumes you've completed the `setting-up-pyutils` skill and have a working processor environment.

Primary use cases:
- Understand EventNtuple branch structure and field access
- Define physics cuts and track selection efficiency
- Extract high-level physics quantities (momentum, angles, energy)
- Fill histograms and analysis distributions
- Build complete analysis processors with parallel file processing

Key outcomes:
- Navigate Mu2e detector data hierarchy (events → tracks → segments)
- Use CutManager to track cut efficiency
- Implement analysis workflows with Vector and Select utilities
- Diagnose and debug data access patterns

---

## EventNtuple Branches and Data Structure

### Important: Branch Selection and Field Access

When working with Mu2e EventNtuple data in pyutils, **only fields that are defined as separate branches can be accessed**. The Vector library cannot reconstruct nested 3D vectors from individual components.

#### Key Rules

1. **All fields must have their own branch**: The Processor only reads branches you explicitly request
2. **Use actual branch names**: Find available branches at https://github.com/Mu2e/EventNtuple/blob/main/doc/branches.md
3. **Nested fields work only with dedicated branches**: For example, `trksegs.mom` works because `trksegs` is a branch with an `mom` XYZVectorF field

#### Common Branch Structure

```
EventNtuple data has a nested hierarchy:
  evt          - Event level (single per event)
  trk          - Track level (variable per event, ~4 tracks per event)
  trksegs      - Segment level (variable per track, ~20 segments per track)
  trksegs.mom  - Momentum vector at each segment (XYZVectorF with .x, .y, .z)
  trksegs.pos  - Position vector at each segment (XYZVectorF with .x, .y, .z)
```

#### Correct vs Incorrect Branch Usage

```python
# ✓ CORRECT: trksegs has mom field with x,y,z components as a branch
momentum = vector.get_mag(data["trksegs"], 'mom')

# ✗ INCORRECT: trksegpars_lh does NOT have a 'mom' field
# (it has LoopHelix parameters like d0, tanDip, rad, lam, cx, cy, phi0, t0)
momentum = vector.get_mag(data["trksegpars_lh"], 'mom')  # ERROR!

# ✓ CORRECT: Access LoopHelix parameters directly (scalars)
d0 = data["trksegpars_lh"]["d0"]
phi0 = data["trksegpars_lh"]["phi0"]

# ✓ CORRECT: Position is a vector field in trksegs
position = vector.get_vector(data["trksegs"], 'pos')  # Returns XYZVector
```

#### Common Branches and Their Fields

| Branch | Type | Fields Available | Purpose |
|--------|------|------------------|---------|
| `trksegs` | Vector-of-vector | `mom` (XYZVectorF), `pos` (XYZVectorF), `time`, `dmom`, `momerr` | Track positions and momenta at detector surfaces |
| `trksegpars_lh` | Vector-of-vector | `d0`, `tanDip`, `rad`, `lam`, `cx`, `cy`, `phi0`, `t0` | LoopHelix fit parameters (looping tracks) |
| `trksegpars_ch` | Vector-of-vector | Same as LoopHelix | CentralHelix fit parameters (field-on cosmics) |
| `trksegpars_kl` | Vector-of-vector | Same as LoopHelix | KinematicLine fit parameters (field-off cosmics) |
| `trkqual` | Vector | `result` | Track fit quality metric (0-1) |
| `trkpid` | Vector | `result` | PID MVA result |
| `crvcoincs` | Vector | `time`, `nHits`, `PEs` | CRV coincidence timing and energy |
| `trk` | Vector | `pdg`, `status`, `nactive`, `nhits` | Track particle properties |

#### Checking Available Fields

```python
# To see what branches and fields are available in your ROOT file:
import uproot
import json

with uproot.open("your_file.root") as f:
    tree = f["EventNtuple/ntuple"]
    
    # List all top-level branches
    print("Branches:", tree.keys())
    
    # For a vector branch, check its structure  
    trksegs = tree["trksegs"]
    print("trksegs type:", trksegs.interpretation)
    
    # Read first entry to see structure
    data = tree.arrays(["trksegs"], entry_stop=1)
    print("Fields in trksegs:", data["trksegs"].fields)  # Shows all available fields
```

---

## Analysis Processor Architecture

### Implementing Key Analysis Methods

Once you have a basic processor working (from `setting-up-pyutils`), implement these core analysis methods:

#### 1. `process_file(file_name)` - Extract and Analyze Data

This is the core method that runs in parallel for each input file. It returns a result dict that `postprocess()` will combine:

```python
import awkward as ak
import gc

def process_file(self, file_name):
    """Process single ROOT file and return analysis results.
    
    This runs in parallel for each file via the Skeleton framework.
    """
    try:
        # Step 1: Create a Processor to extract raw data from ROOT file
        processor = Processor(
            use_remote=self.use_remote,
            location=self.location,
            verbosity=0
        )
        
        # Load nested data: events × tracks × segments
        data = processor.process_data(
            file_name=file_name,
            branches=self.branches
        )
        
        # Step 2: Define cuts using CutManager
        cut_manager = CutManager(verbosity=0)
        self.define_cuts(data, cut_manager)
        
        # Step 3: Apply cuts to filter data
        filtered_data = self.apply_cuts(data, cut_manager)
        
        # Step 4: Fill analysis histograms
        self.fill_histograms(filtered_data)
        
        # Step 5: Get cut statistics
        cut_stats = cut_manager.get_cut_flow()
        
        # Clean up memory
        gc.collect()
        
        return {
            "filtered_data": filtered_data,
            "cut_stats": cut_stats
        }
    
    except Exception as e:
        self.logger.log(f"Error processing {file_name}: {e}", "error")
        return None
```

#### 2. `define_cuts(data, cut_manager)` - Set Up Selection Cuts

Use `CutManager` to define analysis cuts at the appropriate level (event, track, or segment):

```python
from pyutils.pyselect import Select

def define_cuts(self, data, cut_manager):
    """Define all analysis cuts with CutManager.
    
    Cuts are defined at track level, but use nested data from segments.
    """
    selector = Select(verbosity=0)
    
    # Identify segments at tracker front (for quality requirements)
    at_trk_front = selector.select_surface(
        data["trkfit"], 
        surface_name="TT_Front"
    )
    
    # Example: Track type cut (electron vs positron)
    if self.sign == "minus":
        is_electron = selector.is_electron(data["trk"])
        cut_manager.add_cut(
            name="is_reco_electron",
            description="Reconstructed track is electron (pdg=11)",
            mask=is_electron,
            active=True  # Enable by default
        )
        data["is_electron"] = is_electron
    
    # Example: Downstream momentum cut
    # Note: These are segment-level measurements, reduced to track level
    within_momentum = (
        (95 < data['trkfit']["trksegs"]["p"]) & 
        (data['trkfit']["trksegs"]["p"] < 115)
    )
    # Reduce segment-level cut to track level (all segments must pass)
    within_momentum = ak.all(~at_trk_front | within_momentum, axis=-1)
    
    cut_manager.add_cut(
        name="in_momentum_range",
        description="95 < momentum < 115 MeV/c",
        mask=within_momentum,
        active=True
    )
    data["in_momentum"] = within_momentum
    
    # Example: Track fit quality
    good_trkqual = selector.select_trkqual(data["trk"], quality=0.2)
    cut_manager.add_cut(
        name="good_trkqual",
        description="Track quality > 0.2",
        mask=good_trkqual,
        active=True
    )
    
    # Example: CRV (Cosmic Ray Veto) timing cut
    dt_threshold = 150  # ns
    trk_times = data['trkfit']["trksegs"]["time"][at_trk_front]
    coinc_times = data["crv"]["crvcoincs.time"]
    
    # Broadcast to compare all track-coincidence pairs
    coinc_broadcast = coinc_times[:, None, None, :]
    trk_broadcast = trk_times[:, :, :, None]
    dt = abs(trk_broadcast - coinc_broadcast)
    
    # Veto: no coincidence within dt_threshold
    no_crv = ~ak.any(dt < dt_threshold, axis=3)
    no_crv = ak.any(no_crv, axis=2)
    
    cut_manager.add_cut(
        name="no_crv_veto",
        description=f"No CRV coincidence within {dt_threshold} ns",
        mask=no_crv,
        active=True
    )

def apply_cuts(self, data, cut_manager, active_only=True):
    """Apply all defined cuts to filter data.
    
    Returns filtered data and cut statistics.
    """
    # Get combined mask from all active cuts
    combined_mask = cut_manager.get_mask(active_only=active_only)
    
    # Apply to track-level data
    filtered_data = data[combined_mask]
    
    return filtered_data
```

#### 3. `fill_histograms(data)` - Analyze Filtered Data

Process the filtered data and fill histograms with high-level quantities:

```python
from pyutils.pyvector import Vector

def begin_job(self):
    """Create histograms for analysis."""
    self.h_momentum = self.create_histogram(
        name="track_momentum",
        title="Track Momentum",
        bins=200,
        low=0,
        high=200
    )
    
    self.h_impact_d0 = self.create_histogram(
        name="track_d0",
        title="Impact Parameter d0",
        bins=100,
        low=-100,
        high=100
    )
    
    self.h_time = self.create_histogram(
        name="track_t0",
        title="Track T0",
        bins=150,
        low=500,
        high=1650
    )

def fill_histograms(self, data):
    """Fill histograms from filtered data using Vector utilities."""
    
    if data is None or len(data) == 0:
        return
    
    selector = Select()
    vector = Vector()
    
    # Select tracker front segments for quality fits
    at_trk_front = selector.select_surface(
        data["trkfit"],
        surface_name="TT_Front"
    )
    
    # Mask to tracker front for higher-quality measurements
    trkfit_front = ak.mask(data['trkfit']["trksegs"], at_trk_front)
    
    # Calculate momentum magnitude using Vector utilities
    mom_mag = vector.get_mag(trkfit_front, 'mom')
    
    # Flatten and fill histogram
    mom_flat = ak.flatten(mom_mag, axis=None)
    for p in mom_flat:
        self.h_momentum.Fill(p)
    
    # Fill d0 distribution
    d0_flat = ak.flatten(
        trkfit_front['trksegpars_lh']['d0'],
        axis=None
    )
    for d0 in d0_flat:
        self.h_impact_d0.Fill(d0)
    
    # Fill time distribution
    time_flat = ak.flatten(trkfit_front["time"], axis=None)
    for t in time_flat:
        self.h_time.Fill(t)
```

#### 4. `postprocess(results)` - Combine Multi-File Results

Called once after all files are processed to combine partial results:

```python
def postprocess(self, results):
    """Combine results from parallel file processing.
    
    Args:
        results: List of dicts from process_file()
    
    Returns:
        Combined results dict
    """
    if not results:
        return None
    
    # Combine filtered data arrays from all files
    arrays_to_combine = []
    cut_flow_list = []
    
    for result in results:
        if result is None:
            continue
        arrays_to_combine.append(result["filtered_data"])
        cut_flow_list.append(result["cut_stats"])
    
    # Concatenate awkward arrays
    combined_data = ak.concatenate(
        arrays_to_combine
    ) if arrays_to_combine else None
    
    # Combine cut flows
    cut_manager = CutManager(verbosity=0)
    combined_cut_flow = cut_manager.combine_cut_flows(
        cut_flow_list,
        format_as_df=False
    )
    
    # Print summary
    df = cut_manager.format_cut_flow(combined_cut_flow)
    print("================== Combined Cut Flow =======================")
    print(df.to_string(index=False))
    df.to_csv("cut_stats.csv", index=False)
    
    return {
        "combined_data": combined_data,
        "combined_cut_flow": combined_cut_flow
    }

def end_job(self):
    """Finalize analysis and save outputs."""
    print(f"\n=== Analysis Summary ===")
    print(f"Total events analyzed")
    self.save_histograms("analysis_output.root")
    self.logger.log("Analysis complete", "success")
```

---

## Complete Example: Mu2e Electron Analysis Processor

Here's a realistic, complete example based on actual Mu2e analysis code that demonstrates the full analysis pattern:

```python
import awkward as ak
import gc
from pyutils.pyprocess import Skeleton, Processor
from pyutils.pylogger import Logger
from pyutils.pycut import CutManager
from pyutils.pyselect import Select
from pyutils.pyvector import Vector

class ElectronAnalysisProcessor(Skeleton):
    """Analyze tracks to select electrons with quality cuts.
    
    This processor demonstrates:
    - Parallel multi-file processing via Skeleton
    - Nested data hierarchy (events → tracks → segments)
    - CutManager for sophisticated cut tracking
    - Vector utilities for momentum calculations
    """
    
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
        
        # Define data branches to read (nested structure)
        self.branches = {
            "evt": ["run", "subrun", "event", "trig_cpr_TrkDe_80m70p"],
            "trk": ["trk.pdg", "trk.status", "trkqual.result", "trkpid.result"],
            "trkfit": ["trksegs", "trksegpars_lh"],
            "crv": ["crvcoincs.time", "crvcoincs.nHits", "crvcoincs.PEs"]
        }
        
        self.logger = Logger(print_prefix="[ElectronAnalysis]", verbosity=1)
        self.selector = Select(verbosity=0)
        self.logger.log("Processor initialized", "info")
    
    def begin_job(self):
        """Set up histograms and counters."""
        self.logger.log("Setting up histograms", "info")
        self.h_momentum = self.create_histogram(
            name="momentum", title="Track Momentum", bins=200, low=0, high=200
        )
        self.h_quality = self.create_histogram(
            name="track_quality", title="Track Fit Quality", bins=100, low=0, high=1
        )
        self.h_time = self.create_histogram(
            name="track_t0", title="Track T0 (Time)", bins=150, low=400, high=1700
        )
        self.h_tracks_per_event = self.create_histogram(
            name="tracks_per_event", title="Electrons per Event", bins=20, low=0, high=20
        )
        self.event_count = 0
    
    def process_file(self, file_name):
        """Process single ROOT file.
        
        Called automatically in parallel for each file.
        """
        try:
            # Load raw data from file
            processor = Processor(
                use_remote=self.use_remote,
                location=self.location,
                verbosity=0
            )
            
            data = processor.process_data(
                file_name=file_name,
                branches=self.branches
            )
            
            # Define and apply cuts
            cut_manager = CutManager(verbosity=0)
            self.define_cuts(data, cut_manager)
            combined_mask = cut_manager.get_mask(active_only=True)
            filtered_data = data[combined_mask]
            
            # Fill histograms
            self.fill_histograms(filtered_data)
            
            # Get cut flow for this file
            cut_stats = cut_manager.get_cut_flow()
            gc.collect()
            
            return {"filtered_data": filtered_data, "cut_stats": cut_stats}
        
        except Exception as e:
            self.logger.log(f"Error in {file_name}: {e}", "error")
            return None
    
    def define_cuts(self, data, cut_manager):
        """Define electron selection cuts."""
        
        # Identify track front segments
        at_trk_front = self.selector.select_surface(
            data["trkfit"], surface_name="TT_Front"
        )
        
        # 1. Electron type cut
        is_electron = self.selector.is_electron(data["trk"])
        cut_manager.add_cut(
            name="is_electron",
            description="Reco track is electron",
            mask=is_electron, active=True
        )
        
        # 2. One electron per event
        one_per_event = ak.sum(is_electron, axis=-1) == 1
        one_per_event, _ = ak.broadcast_arrays(one_per_event, is_electron)
        cut_manager.add_cut(
            name="one_electron_per_event",
            description="Exactly one electron per event",
            mask=one_per_event, active=True
        )
        
        # 3. Track quality cut
        good_quality = self.selector.select_trkqual(data["trk"], quality=0.2)
        cut_manager.add_cut(
            name="good_trkqual", description="Track quality > 0.2",
            mask=good_quality, active=True
        )
        
        # 4. Momentum range
        vector = Vector(verbosity=0)
        trkfit_front = ak.mask(data['trkfit']["trksegs"], at_trk_front)
        mom_mag = vector.get_mag(trkfit_front, 'mom')
        mom_range = (95 < mom_mag) & (mom_mag < 115)
        mom_range = ak.all(~at_trk_front | mom_range, axis=-1)
        cut_manager.add_cut(
            name="momentum_range",
            description="95 < p < 115 MeV/c",
            mask=mom_range, active=True
        )
        
        # 5. Time window (tracker T0)
        trk_time = data['trkfit']["trksegs"]["time"]
        within_time = (500 < trk_time) & (trk_time < 1650)
        within_time = ak.all(~at_trk_front | within_time, axis=-1)
        cut_manager.add_cut(
            name="within_time", description="500 < T0 < 1650 ns",
            mask=within_time, active=True
        )
        
        # 6. CRV veto (no cosmic coincidence)
        dt_threshold = 150  # ns
        trk_times = data['trkfit']["trksegs"]["time"][at_trk_front]
        coinc_times = data["crv"]["crvcoincs.time"]
        coinc_broadcast = coinc_times[:, None, None, :]
        trk_broadcast = trk_times[:, :, :, None]
        dt = ak.abs(trk_broadcast - coinc_broadcast)
        any_coinc = ak.any(dt < dt_threshold, axis=3)
        veto = ak.any(any_coinc, axis=2)
        cut_manager.add_cut(
            name="no_crv_veto",
            description="No CRV coincidence within 150 ns",
            mask=~veto, active=True
        )
    
    def fill_histograms(self, data):
        """Fill histograms from filtered data."""
        if data is None or len(data) == 0:
            return
        
        at_trk_front = self.selector.select_surface(data["trkfit"], surface_name="TT_Front")
        trkfit_front = ak.mask(data['trkfit']["trksegs"], at_trk_front)
        
        # Fill distributions
        vector = Vector()
        mom_mag = vector.get_mag(trkfit_front, 'mom')
        for p in ak.flatten(mom_mag, axis=None):
            self.h_momentum.Fill(float(p))
        
        for q in ak.flatten(data["trk"]["trkqual.result"], axis=None):
            self.h_quality.Fill(float(q))
        
        for t in ak.flatten(trkfit_front["time"], axis=None):
            self.h_time.Fill(float(t))
        
        for count in ak.num(data["trk"], axis=-1):
            self.h_tracks_per_event.Fill(count)
        
        self.event_count += len(data)
    
    def postprocess(self, results):
        """Combine results from all files."""
        if not results:
            return None
        
        arrays_to_combine = []
        cut_flows = []
        
        for result in results:
            if result is None:
                continue
            arrays_to_combine.append(result["filtered_data"])
            cut_flows.append(result["cut_stats"])
        
        combined_data = ak.concatenate(arrays_to_combine) if arrays_to_combine else None
        
        # Combine cut flows
        cut_manager = CutManager(verbosity=0)
        combined_cut_flow = cut_manager.combine_cut_flows(cut_flows, format_as_df=False)
        df = cut_manager.format_cut_flow(combined_cut_flow)
        
        print("\n" + "="*60)
        print("Combined Cut Flow (All Files)")
        print("="*60)
        print(df.to_string(index=False))
        df.to_csv("cut_flow_summary.csv", index=False)
        
        return {"combined_data": combined_data, "combined_cut_flow": combined_cut_flow}
    
    def end_job(self):
        """Finalize analysis."""
        self.logger.log(f"Total events: {self.event_count}", "info")
        self.save_histograms("electron_analysis.root")
        self.logger.log("Saved to electron_analysis.root", "success")

# Usage
if __name__ == "__main__":
    processor = ElectronAnalysisProcessor("my_file_list.txt", jobs=4, location='disk')
    results = processor.execute()
    print(f"Total electrons selected: {len(results['combined_data'])}")
```

---

## Common Analysis Patterns

### 1. Working with Awkward Arrays for Nested Data

Mu2e data has nested structure: events → tracks → segments. Use Awkward Arrays for efficient operations:

```python
import awkward as ak

# Select at specific level (segment-level mask from track-level requirement)
at_trk_front = selector.select_surface(data["trkfit"], surface_name="TT_Front")

# Apply segment-level cut
within_momentum = (95 < data['trkfit']["trksegs"]["p"]) & (data['trkfit']["trksegs"]["p"] < 115)

# Reduce to track level (all segments at front must pass)
within_momentum = ak.all(~at_trk_front | within_momentum, axis=-1)

# Mask and filter
trkfit_front = ak.mask(data['trkfit']["trksegs"], at_trk_front)
filtered_data = data[within_momentum]

# Flatten for histogram filling
flat_values = ak.flatten(interesting_variable, axis=None)
for val in flat_values:
    histogram.Fill(float(val))
```

### 2. Broadcasting for Multi-Level Comparisons

Compare across multiple hierarchies (tracks vs coincidences):

```python
# Track times and coincidence times have different dimensions
trk_times = data['trkfit']["trksegs"]["time"][at_trk_front]  # events × tracks × segments
coinc_times = data["crv"]["crvcoincs.time"]                   # events × coincidences

# Broadcast to match shapes for element-wise comparison
coinc_broadcast = coinc_times[:, None, None, :]       # events × 1 × 1 × coincidences
trk_broadcast = trk_times[:, :, :, None]              # events × tracks × segments × 1

# Now can compute element-wise
dt = ak.abs(trk_broadcast - coinc_broadcast)          # events × tracks × segments × coincidences

# Reduce dimensions appropriately
within_threshold = dt < 150                            # element-wise comparison
any_coinc = ak.any(within_threshold, axis=3)          # any coincidence within threshold?
veto = ak.any(any_coinc, axis=2)                      # any track from this event?
```

### 3. Using Vector Utilities for Momentum Calculations

Leverage `pyutils.pyvector.Vector` for robust physics quantities:

#### Vector API Reference

```python
from pyutils.pyvector import Vector

vector = Vector(verbosity=0)

# Primary methods (use positional arguments, not keyword arguments):

# Get magnitude of 3-vector field (e.g., momentum)
# Signature: get_mag(data, field_name)
magnitude = vector.get_mag(segment_data, 'mom')      # Returns scalar magnitude

# Get vector components
# Signature: get_vector(data, field_name)
vec = vector.get_vector(segment_data, 'mom')         # Returns vector with .x, .y, .z, .rho
px, py, pz = vec.x, vec.y, vec.z                     # Access components
pt = vec.rho                                           # Transverse momentum
```

#### Common Use Cases

```python
from pyutils.pyvector import Vector
import awkward as ak

vector = Vector(verbosity=0)
selector = Select(verbosity=0)

# Example 1: Momentum calculation at tracker front
at_trk_front = selector.select_surface(data["trkfit"], surface_name="TT_Front")
trkfit_front = ak.mask(data['trkfit']["trksegpars_lh"], at_trk_front)

# Calculate momentum magnitude (use positional argument)
mom_mag = vector.get_mag(trkfit_front, 'mom')

# Example 2: Momentum components
mom_vector = vector.get_vector(trkfit_front, 'mom')
px = mom_vector.x
py = mom_vector.y
pz = mom_vector.z
pt = mom_vector.rho                    # Transverse momentum: sqrt(px^2 + py^2)

# Example 3: Safe division (handles zeros)
pz_over_pt = ak.where(pt > 0, pz / pt, ak.zeros_like(pt))

# Example 4: Flatten for histogram filling
mom_flat = ak.flatten(mom_mag, axis=None)
for p in mom_flat:
    histogram.Fill(float(p))
```

#### Important Notes

- **Use positional arguments**, not keyword arguments: `get_mag(data, 'mom')` ✓ not `get_mag(data, field_name='mom')` ✗
- Works with awkward arrays at any nesting level
- Returns masked arrays when input is masked
- Field names depend on branch: `'mom'` for momentum, `'pos'` for position, etc.

### 4. Cut Flow Management with CutManager

Track efficiency across all cuts:

```python
from pyutils.pycut import CutManager

cut_manager = CutManager(verbosity=1)

# Add cuts with clear descriptions
cut_manager.add_cut(
    name="is_electron",
    description="Reco track matches electron hypothesis",
    mask=is_electron,
    active=True
)

cut_manager.add_cut(
    name="good_quality",
    description="Track fit quality > 0.2",
    mask=good_quality,
    active=True
)

# Combine all active cuts into a single boolean mask
combined_mask = cut_manager.get_mask(active_only=True)  # Returns boolean array

# Filter data using combined mask
filtered_data = data[combined_mask]

# Create cut flow statistics (requires the full data array)
cut_flow = cut_manager.create_cut_flow(data)

# Format cut flow as pandas DataFrame
df_cut_flow = cut_manager.format_cut_flow(cut_flow)
df_cut_flow.to_csv("cut_flow.csv", index=False)
print(df_cut_flow.to_string(index=False))

# Combine cut flows from multiple files (parallel processing)
combined_flow = cut_manager.combine_cut_flows([flow1, flow2, flow3], format_as_df=True)
```

### 5. Using Select Utilities for Common Operations

The `Select` class provides specialized selectors:

```python
from pyutils.pyselect import Select

selector = Select(verbosity=0)

# Surface selections (TT_Front, TT_Mid, TT_Back, ST_Foils, OPA, etc.)
at_trk_front = selector.select_surface(data["trkfit"], surface_name="TT_Front")
has_st = selector.has_ST(data['trkfit'])
has_opa = selector.has_OPA(data['trkfit'])

# Track type selections
is_electron = selector.is_electron(data["trk"])
is_positron = selector.is_positron(data["trk"])
is_downstream = selector.is_downstream(data['trkfit'])

# Quality selections
good_quality = selector.select_trkqual(data["trk"], quality=0.2)
good_pid = selector.select_trkpid(data["trk"], value=0.638)
has_hits = selector.has_n_hits(data["trk"], n_hits=20)

# Trigger selection
has_trigger = selector.get_triggers(
    data["evt"],
    ["trig_cpr_TrkDe_80m70p", "trig_apr_TrkDe_80m70p"]
)
```

### 6. Memory Management in Parallel Processing

Process multiple files efficiently:

```python
class MyProcessor(Skeleton):
    def process_file(self, file_name):
        # Each file runs in separate process
        try:
            data = processor.process_data(file_name, branches)
            results = analyze(data)
            return results
        finally:
            import gc
            gc.collect()  # Force cleanup after each file
    
    def postprocess(self, results):
        # Combine all results (runs in main process)
        combined = concatenate_results(results)
        return combined
```

### 7. Error Handling for Nested Data

Safely work with deeply nested structures:

```python
try:
    # Check before accessing deeply nested data
    if data is None or len(data) == 0:
        return
    
    # Use ak.nan_to_none and ak.drop_none for cleanup
    times = ak.nan_to_none(data['time'])
    times = ak.drop_none(times)
    
    # Guard against missing branches
    try:
        pe = data["crv"]["crvcoincs.PEs"]
        nh = data["crv"]["crvcoincs.nHits"]
    except (KeyError, AttributeError):
        # Branch doesn't exist; use defaults
        pe = ak.ones_like(data["crv"]["crvcoincs.time"]) * 0
        nh = ak.zeros_like(data["crv"]["crvcoincs.time"])

except Exception as e:
    self.logger.log(f"Error in data processing: {e}", "error")
    return None
```

---

## Troubleshooting Physics Analysis

### Issue: Cut flow shows all zeros

**Problem:** No events pass any cuts

**Solution:** Debug cut definitions step-by-step:

```python
# Add diagnostic cuts to see where events fail
cut_manager.add_cut(
    name="debug_has_data",
    description="Events with at least one track",
    mask=ak.num(data["trk"], axis=-1) > 0,
    active=True
)

# Print cut statistics after defining
flow = cut_manager.get_cut_flow()
df = cut_manager.format_cut_flow(flow)
print(df)  # See raw numbers before combining
```

### Issue: KeyError when accessing nested branches

**Problem:** `data["trkfit"]["trksegs"]["nonexistent"]` fails

**Solution:** Check available branches:

```python
# List available branches
print(data["trkfit"].fields)  # Shows nested field names

# Use try/except for optional data
try:
    field = data["trkfit"]["trksegpars_lh"]["t0err"]
except (KeyError, AttributeError):
    logger.log("Branch not available, skipping", "warning")
    field = None
```

### Issue: Awkward Array dimension mismatch

**Problem:** `ValueError: inconsistent data` when concatenating results

**Solution:** Ensure output structure is consistent:

```python
# In postprocess, validate all results have same structure
for i, result in enumerate(results):
    if result is None:
        continue
    print(f"File {i}: {result['filtered_data'].fields}")

# Then concatenate only valid results
valid_results = [r for r in results if r is not None]
combined = ak.concatenate([r['filtered_data'] for r in valid_results])
```

### Issue: Memory overflow with large files

**Problem:** Processing many large ROOT files runs out of memory

**Solution:** Monitor and control data loading:

```python
def process_file(self, file_name):
    """Process with memory control."""
    try:
        # Load only necessary branches
        data = processor.process_data(
            file_name, 
            branches=self.branches  # Minimize branches
        )
        
        # Process immediately, don't accumulate
        results = analyze(data)
        return results
    finally:
        import gc
        del data  # Explicit cleanup
        gc.collect()
```

### Issue: Vector magnitude calculation returns NaN

**Problem:** `vector.get_mag()` returns empty or NaN values

**Solution:** Check momentum field availability and masking:

```python
# Verify momentum branch is available
print("Available fields:", data["trksegs"].fields)

# Check for NaN values before calculation
mom_raw = data["trkfit"]["trksegs"]["mom"]
print(f"NaN count: {ak.sum(ak.is_nan(mom_raw), axis=-1)}")

# Use safe calculation
vector = Vector(verbosity=1)  # Enable debug output
mom_mag = vector.get_mag(data["trkfit"]["trksegs"], 'mom')
print(f"Result type: {type(mom_mag)}")
print(f"Sample values: {mom_mag[0, :5]}")
```

---

## Key Helper Modules

- **`pyutils.pyprocess.Skeleton`** - Base processor class for parallel file processing
- **`pyutils.pyprocess.Processor`** - Low-level data extraction from ROOT files
- **`pyutils.pycut.CutManager`** - Track cut efficiency and statistics
- **`pyutils.pyselect.Select`** - Specialized selection functions (surfaces, particle types)
- **`pyutils.pyvector.Vector`** - Physics quantity calculations (momentum, angles)
- **`pyutils.pylogger.Logger`** - Structured logging with verbosity levels

---

## Resources

- **PyUtils Repository**: https://github.com/Mu2e/pyutils
- **EventNtuple Branches**: https://github.com/Mu2e/EventNtuple/blob/main/doc/branches.md
- **Mu2e Offline Wiki**: https://mu2ewiki.fnal.gov/wiki/Main_Page
- **Awkward Array Docs**: https://awkward-array.org/
- **ROOT Tutorial**: https://root.cern/doc/ROOTUsersGuide/

---

## See Also

- `setting-up-pyutils` - Installation and first processor setup
- `coding-with-metacat` - Querying Mu2e ROOT files
- `finding-data-sam` - Alternative data discovery method
- `understanding-data-handling` - Mu2e data ecosystem overview
