# ParetoMetaDecision

## 1. Overview

### 1.1 What is ParetoMetaDecision?

**ParetoMetaDecision** is a decision-optimization framework for discovering, evaluating, and selecting **interpretable decision rules** under **multiple competing objectives**. Instead of training predictive models, the system directly optimizes **decision sentences** (e.g., logical rules compiled from an AST) to produce a **Pareto set** of non-dominated alternatives that trade off performance, risk, operational exposure, and interpretability.

The framework is designed as a **general-purpose engine**: domains are integrated via plugins that define data sources, feature construction, admissible decision primitives, and evaluation procedures. The optimization core remains unchanged across domains, enabling reproducible decision optimization in settings ranging from market microstructure signals to clinical rule-based decision support or any domain it can be define.

---

### 1.2 Motivation: From Prediction to Decision Optimization

Many real-world decision systems fail not because prediction is impossible, but because **the decision process itself is not optimized**: rules are static, objectives are implicit, and operational constraints (e.g., frequency, exposure, cost) are handled post hoc. ParetoMetaDecision addresses this gap by framing decision-making as a **prescriptive, multi-objective optimization problem**:

- **Decision quality is evaluated end-to-end** using domain-specific execution semantics (not proxy labels).
- **Trade-offs are explicit** through Pareto fronts rather than collapsed into a single scalar score.
- **Interpretability is enforced by construction** via a constrained decision language and complexity measures.
- **Operational realism is modeled** through costs, horizons, and activity/exposure constraints.

The result is a set of decision rules that are not only effective, but also **actionable**, **auditable**, and **fit for deployment**.

---

### 1.3 Key Principles

1. **Decision-first, not prediction-first**  
   The primary artifact is an interpretable decision program (sentence), optimized against objectives that reflect the real decision context.

2. **Multi-objective optimization with Pareto alternatives**  
   The system outputs a Pareto set of non-dominated decision rules, enabling principled selection based on preferences and constraints.

3. **Interpretability by design**  
   Decision rules are expressed in a constrained AST-based language, with explicit complexity accounting to prevent uncontrolled growth.

4. **Governed search across rounds (meta-decision layer)**  
   Optimization is executed in governed rounds. A governance mechanism selects high-level actions (e.g., EXPLOIT, EXPLORE, EXPAND_LANGUAGE, STOP) based on observed progress and stagnation—**controlling the search process**, not the domain outcomes.

5. **Deterministic validation and reproducibility**  
   Seeds, evaluation semantics, and governance constraints are explicit. AI-in-the-loop governance (when enabled) is bounded by allowlists, parameter clamps, cooldowns, and deterministic fallback policies.

6. **Plugin-based generality**  
   Domains provide data, features, decision primitives, and evaluators via plugins; the optimization and governance layers remain general and reusable.


## 2. Core Concepts

### 2.1 Decision-Centric Optimization

ParetoMetaDecision treats **decision-making itself** as the primary optimization object. Rather than optimizing model parameters to improve predictive accuracy, the framework optimizes **explicit decision rules** that map observed states to actions. Each candidate rule is evaluated end-to-end according to domain execution semantics, ensuring that optimization directly reflects the consequences of acting on the rule in practice.

This decision-centric view is particularly suited to domains where actions incur costs, risks, or operational constraints that cannot be adequately captured by prediction metrics alone.

---

### 2.2 Interpretable Decision Language (AST-based)

Decisions are represented using a **constrained, interpretable language** compiled into an **Abstract Syntax Tree (AST)**. The language supports logical composition (e.g., AND, OR, NOT) and domain-specific primitives (e.g., thresholds, trend conditions), while enforcing structural constraints that guarantee interpretability.

Each AST exposes:
- **Executable semantics** for evaluation on data,
- **Canonical representations** for caching and deduplication,
- **Structural complexity measures** used as optimization objectives or constraints.

Interpretability is therefore not a post-processing step, but a **first-class property** of the search space.

---

### 2.3 Multi-objective Evaluation and Pareto Fronts

Decision rules are evaluated against **multiple, potentially conflicting objectives**, such as performance, risk, operational exposure, and complexity. These objectives are optimized simultaneously using evolutionary multi-objective optimization, producing a **Pareto front** of non-dominated decision rules.

This approach avoids arbitrary scalarization and makes trade-offs explicit. Users and downstream systems can select among Pareto-optimal alternatives based on preferences, constraints, or governance policies, without rerunning optimization.

---

### 2.4 Governance vs. Decision-Making

A central concept in ParetoMetaDecision is the **strict separation between decision-making and governance**.

- **Decision-making** concerns *what* rule to apply in a given state and is entirely determined by the optimized decision sentences.
- **Governance** concerns *how* the optimization process evolves over time, including exploration pressure, parameter tuning, language expansion, and stopping criteria.

The governance layer operates at the **meta-decision level**: it observes aggregated optimization state and selects control actions that regulate subsequent search rounds. It does not generate decision rules, modify evaluations, or intervene in domain semantics. This separation preserves methodological clarity, interpretability, and reproducibility.


## 3. System Architecture

### 3.1 High-Level Architecture

ParetoMetaDecision is organized as a modular system composed of four clearly separated layers: **domain integration**, **decision representation**, **optimization**, and **governance**. Domain-specific logic (data access, feature construction, decision primitives, and evaluation semantics) is encapsulated in plugins, while the optimization and governance layers remain domain-agnostic.

At runtime, the system orchestrates these layers to execute a sequence of governed optimization rounds. Each round produces a population of candidate decision rules, evaluates them under fixed semantics, and exposes a summarized optimization state to the governance layer. This architecture enables reuse across domains, controlled extensibility, and clear separation of responsibilities.

---

### 3.2 Round-Based Optimization Loop

Optimization proceeds in discrete **rounds**, each consisting of a complete evolutionary multi-objective search executed under fixed evaluation settings. Within a round, candidate decision rules are generated, evaluated, and ranked solely based on the defined objectives and constraints.

After each round, the resulting population is aggregated into a compact representation capturing key indicators such as Pareto front statistics, best achieved objective values, stagnation signals, diversity measures, and rule complexity summaries. This aggregated state forms the basis for governance decisions that regulate how subsequent rounds are conducted, without retroactively affecting the evaluations already performed.

---

### 3.3 AI-in-the-loop Governance Layer

The governance layer operates as a **process-level controller** that regulates the optimization loop across rounds. When enabled, an AI component observes the aggregated optimization state and proposes a governance action selected from a restricted and predefined action space (e.g., EXPLORE, EXPLOIT, EXPAND_LANGUAGE, STOP).

Crucially, the AI component does not generate candidate decision rules, modify evaluation semantics, or influence objective computations. Its role is limited to selecting high-level control actions that adjust search parameters, exploration pressure, or admissible language constructs for future rounds. This design positions the AI strictly at the meta-decision level, ensuring transparency and methodological control.

---

### 3.4 Deterministic Validation and Safety Controls

All governance actions—whether proposed by an AI component or by a deterministic policy—are processed through a validation layer that enforces safety, reproducibility, and compliance constraints. This layer applies allowlists for admissible actions, clamps parameter updates within predefined bounds, enforces cooldown periods to prevent unstable oscillations, and verifies authorization for language extensions.

If a proposed action fails validation or if the AI component is unavailable, a deterministic fallback policy is applied. As a result, the optimization process remains robust, reproducible, and fully controllable, even in the presence of stochastic optimization operators or AI-assisted governance.


## 4. Decision Language

### 4.1 Abstract Syntax Tree (AST) Representation

Decision rules in ParetoMetaDecision are represented as **Abstract Syntax Trees (ASTs)**. Each AST encodes a complete decision sentence, composed of logical operators and domain-specific primitives, and can be deterministically compiled into an executable program. This representation enables structural reasoning about decisions, facilitates controlled composition, and provides a natural basis for measuring interpretability.

Every AST exposes three essential capabilities: (i) execution over domain data, (ii) canonicalization for equivalence checking and caching, and (iii) structural complexity estimation. These properties allow the system to evaluate decisions consistently, avoid redundant evaluations, and explicitly control rule growth during optimization.

---

### 4.2 Logical Operators and Functions

The decision language supports a minimal yet expressive set of logical operators (e.g., AND, OR, NOT, TRUE) combined with **domain-defined decision primitives**. Primitives may include threshold conditions, trend indicators, or other interpretable constructs provided by the domain plugin.

The language is intentionally constrained: only explicitly enabled operators and functions are admissible at any given time. This restriction ensures that all generated rules remain interpretable, auditable, and aligned with domain semantics.

---

### 4.3 Rule Complexity and Interpretability

Interpretability is enforced by design through **explicit complexity accounting**. Each decision rule is assigned a structural complexity score derived from its AST, reflecting factors such as depth, number of nodes, and logical composition.

Complexity can be treated as an optimization objective, a constraint, or a reporting dimension. By integrating complexity directly into the optimization process, ParetoMetaDecision prevents uncontrolled rule growth and produces decision alternatives that balance effectiveness with simplicity.

---

### 4.4 Language Expansion Mechanism

The decision language is not static. ParetoMetaDecision supports **controlled language expansion**, whereby additional operators or primitives can be enabled across rounds as part of the governance process. Language expansion is treated as a governance action and is subject to explicit authorization and cache invalidation.

This mechanism allows the system to start from a conservative, highly interpretable language and progressively increase expressiveness only when justified by observed optimization stagnation or unmet objectives, maintaining a disciplined trade-off between expressiveness and interpretability.


## 5. Optimization Engine

### 5.1 Evolutionary Multi-objective Optimization (NSGA-II)

ParetoMetaDecision employs **evolutionary multi-objective optimization** as its core search mechanism, with NSGA-II as the default algorithm. This choice reflects the need to explore large, non-convex, and discontinuous decision spaces while explicitly preserving trade-offs among competing objectives.

Within each optimization round, candidate decision rules encoded as ASTs are evolved through variation operators adapted to the decision language. Selection is driven by Pareto dominance and diversity preservation, ensuring that the resulting population approximates the Pareto front of non-dominated decision rules under the specified objectives.

---

### 5.2 Objectives and Constraints

Decision rules are evaluated against multiple objectives that reflect both performance and operational considerations. Typical objectives include measures of decision effectiveness, risk or variability, operational exposure or activity, and rule complexity. The framework allows objectives to be maximized or minimized as appropriate and supports domain-specific validity filters to exclude degenerate or impractical solutions.

Constraints are handled explicitly through evaluation semantics and post-evaluation filtering, ensuring that only admissible decision rules contribute to the optimization process. This design maintains clarity between what constitutes a valid decision and how trade-offs among valid decisions are optimized.

---

### 5.3 Search Space and Parameterization

The search space is defined by the current decision language, its admissible operators and primitives, and their associated parameters. Continuous parameters (e.g., thresholds) and discrete choices (e.g., operator selection) are jointly optimized within the evolutionary framework.

Algorithmic parameters such as population size, number of generations, crossover and mutation probabilities, and distribution indices are explicitly configurable and may be adjusted across rounds by the governance layer. This parameterization enables adaptive control of search behavior without altering evaluation semantics or decision representations.

---

### 5.4 Exploration vs. Exploitation Control

Balancing exploration and exploitation is treated as a first-class concern in ParetoMetaDecision. Exploration promotes diversity and discovery of novel decision structures, while exploitation focuses computational effort on refining promising regions of the search space.

This balance is managed at the round level through governance actions that adjust evolutionary parameters, reseeding strategies, or exploration pressure. By externalizing exploration–exploitation control from the core optimizer and placing it under governance, the framework achieves flexible yet disciplined adaptation of search dynamics across optimization rounds.

## 6. Governance Mechanism

### 6.1 Governance Actions (EXPLORE, EXPLOIT, EXPAND_LANGUAGE, STOP)

Governance in ParetoMetaDecision is expressed through a small, explicit set of **high-level control actions** that regulate the optimization process across rounds. Typical actions include:
- **EXPLORE**, to increase diversity and broaden the search;
- **EXPLOIT**, to intensify search around promising regions;
- **EXPAND_LANGUAGE**, to enable additional decision primitives or operators when expressiveness becomes limiting;
- **STOP**, to terminate the process when sustained stagnation or predefined criteria are met.

These actions do not alter decision semantics or evaluation functions; they strictly control *how* the search proceeds.

---

### 6.2 State Aggregation and Stagnation Detection

After each round, the optimizer’s output is summarized into an aggregated state that captures essential progress indicators, such as Pareto front quality, best objective values, diversity measures, and complexity trends. Stagnation detection relies on these summaries to identify sustained lack of improvement.

This aggregation deliberately abstracts away individual solutions, providing a concise and interpretable snapshot of optimization dynamics suitable for governance decisions.

---

### 6.3 AI Governance Component

When enabled, an AI component observes the aggregated state and proposes a governance action from the predefined action set. The AI operates strictly at the **meta-decision level**, reasoning about optimization dynamics rather than domain outcomes.

Its inputs and outputs are governed by a strict contract, ensuring that proposals remain interpretable, bounded, and aligned with methodological constraints.

---

### 6.4 Deterministic Fallback Policies

To guarantee robustness and reproducibility, ParetoMetaDecision includes deterministic fallback policies that are applied whenever AI output is invalid, unavailable, or non-compliant. These policies implement conservative, rule-based governance decisions that maintain forward progress without compromising control.

As a result, the system remains fully operational and reproducible regardless of AI availability, reinforcing governance as a controllable and auditable component of the optimization process.


## 7. Reproducibility and Determinism

This project is designed so that **reproducibility is a first-class property**, not an afterthought. All experimental results can be exactly reproduced given the same configuration, data, and execution context.

### 7.1 Random Seeding Strategy

All stochastic components are governed by an **explicit and hierarchical seeding strategy**.

- A **global master seed** defines each experimental run.
- Deterministic sub-seeds are derived for:
  - Population initialization  
  - Variation operators (mutation, crossover, sampling)  
  - Evaluation ordering and auxiliary stochastic processes
- No component relies on implicit or global RNG state.

This guarantees that:
- The same configuration always produces the same stochastic sequence.
- Different runs are fully isolated and comparable.
- Exploratory randomness is controlled, intentional, and traceable.

---

### 7.2 Fixed Evaluation Semantics

Evaluation follows a **strictly deterministic and optimizer-independent semantics**.

- Each candidate (rule, policy, parameter set) is evaluated by a **pure function**.
- The evaluator:
  - Consumes only immutable or versioned data
  - Has no side effects or hidden state
  - Is independent of evaluation order or optimizer internals
- The output is a **complete and self-contained metric vector**.

Identical inputs always yield identical outputs, enabling fair comparison across algorithms, runs, and experiments.

---

### 7.3 Governance Contracts and Validation

Reproducibility is enforced through **explicit governance contracts**.

Each experiment is validated against:
- Configuration completeness (parameters, bounds, objectives)
- Metric definitions and optimization direction
- Decision validity and domain constraints

Invalid or ill-defined experiments are rejected before execution, preventing silent inconsistencies and ensuring experimental integrity.

---

### 7.4 Experimental Reproducibility Guarantees

The system provides **strong reproducibility guarantees**:

- Any experiment can be exactly replayed using:
  - The same configuration files
  - The same dataset version
  - The same master seed
- Results are invariant to:
  - Execution order
  - Optimizer choice
  - Hardware parallelism (within floating-point limits)

These guarantees make the framework suitable for **scientific publication, auditing, and long-term governance of decision systems**.


## 8. Experimental Workflow

This section describes the end-to-end experimental workflow adopted in this project. The workflow is intentionally **structured, governed, and reproducible**, ensuring that all experimental results are traceable, comparable, and scientifically valid.

---

### 8.1 Data Requirements and Preprocessing

Experiments operate on **explicitly defined and versioned datasets**.

- All data sources are declared before execution.
- Input data is treated as **read-only** during optimization.
- Any preprocessing step (filtering, aggregation, normalization) is:
  - Deterministic
  - Fully specified in configuration files
  - Executed prior to optimization

This guarantees that the optimization process never alters the data it evaluates, and that preprocessing does not introduce hidden variability.

---

### 8.2 Evaluation Metrics

Each experiment defines a **fixed and explicit set of evaluation metrics**.

- Metrics are computed for every candidate solution.
- Each metric has:
  - A clear semantic definition
  - A fixed optimization direction (minimize / maximize)
  - A consistent numerical scale across runs
- Metrics are independent of the optimizer and evaluation order.

The resulting metric vectors provide a stable basis for multi-objective comparison, dominance analysis, and post-hoc evaluation.

---

### 8.3 Running Governed Optimization Rounds

Optimization is executed in **governed rounds**, each corresponding to a well-defined experimental configuration.

- Each round specifies:
  - Parameter space and constraints
  - Optimizer and control parameters
  - Random seed and execution policy
- All evaluations are validated against governance contracts.
- Invalid configurations or results are rejected immediately.

This structure enables controlled experimentation while preventing uncontrolled or ill-defined optimization runs.

---

### 8.4 Result Collection and Analysis

All experimental outputs are **systematically collected and stored**.

- Evaluated candidates and metric vectors are persisted.
- Metadata includes:
  - Configuration identifiers
  - Dataset version
  - Seed and execution context
- Results can be:
  - Replayed
  - Compared across optimizers
  - Analyzed post-hoc using dominance, Pareto fronts, or statistical summaries

This ensures that conclusions are derived from a complete and auditable experimental record.


## 9. Visualization and Analysis

Visualization and analysis are treated as **analytical instruments**, not merely presentation tools. All visual outputs are derived directly from recorded experimental artifacts, ensuring consistency, traceability, and analytical validity.

---

### 9.1 Outcome Space Visualizations

The primary analytical view is the **outcome (objective) space**.

- Multi-objective results are visualized using:
  - Scatter plots of metric vectors
  - Pareto front and dominance structures
- All points correspond to fully evaluated and validated candidates.
- Visualizations are invariant to optimizer choice and evaluation order.

These views support comparative analysis, trade-off inspection, and identification of non-dominated regions.

---

### 9.2 Decision Space and Activity Analysis

Beyond outcomes, the system supports analysis of the **decision space** and evaluation activity.

- Parameter distributions and coverage are visualized.
- Evaluation density highlights explored and underexplored regions.
- Decision activity metrics (e.g., frequency, exposure, activation rate) can be inspected alongside outcomes.

This enables diagnosis of search behavior and detection of blind spots or over-explored regions.

---

### 9.3 Interpretability and Complexity Analysis

Each candidate solution is analyzed for **interpretability and structural complexity**.

- Complexity indicators may include:
  - Number of parameters or conditions
  - Structural depth or rule composition
- Interpretability metrics are treated as first-class analytical dimensions.
- Complexity–performance trade-offs can be directly visualized.

This ensures that high-performing solutions remain analyzable and suitable for human-in-the-loop decision contexts.

---

### 9.4 Cross-Round Dynamics

The system supports analysis across multiple optimization rounds.

- Evolution of metric distributions over rounds can be tracked.
- Stability and convergence of Pareto fronts are inspected.
- Cross-round comparisons reveal:
  - Performance gains
  - Structural drift
  - Effects of governance or parameter changes

These analyses provide insight into the temporal behavior of the optimization process, beyond single-run results.

## 10. Use Cases

The framework is domain-agnostic by design, but it has been validated on **representative, high-impact decision domains**. These use cases illustrate how the same governed optimization pipeline adapts to different data, decision semantics, and evaluation criteria.

---

### 10.1 Financial Decision Optimization (Order Flow / L2)

In financial markets, the framework is applied to **decision optimization under high-frequency, high-noise conditions**.

- Decisions are derived from order flow and Level-2 (L2) market data.
- Candidate solutions include:
  - Rule-based signals
  - Parametric decision policies
- Evaluation metrics typically cover:
  - Expected return or utility
  - Risk and volatility exposure
  - Decision frequency and market participation

The governed setup ensures that all strategies are evaluated consistently, avoiding look-ahead bias and uncontrolled stochastic effects.

---

### 10.2 Clinical Decision Support (Rules and Thresholds)

In clinical contexts, the framework supports **interpretable and auditable decision rules**.

- Decisions are expressed as:
  - Threshold-based rules
  - Logical combinations of clinical parameters
- Objectives may include:
  - Diagnostic yield
  - False positive control
  - Resource utilization and cost
- Interpretability and simplicity are treated as explicit optimization criteria.

This enables systematic improvement of clinical rules while preserving transparency and medical accountability.

---

### 10.3 General Decision Optimization Domains

Beyond finance and healthcare, the framework applies to **generic decision optimization problems**.

- Any domain that can define:
  - A decision representation
  - An evaluation function
  - One or more objectives
- Examples include:
  - Policy selection
  - Resource allocation
  - Rule discovery in structured data

By separating decision representation, evaluation semantics, and optimization logic, the framework remains extensible and reusable across domains.


## 11. Positioning and Scope

This section clarifies the **conceptual positioning** of ParetoMetaDecision and delineates its scope. The framework is intentionally focused on **optimizing decisions**, not on learning predictive models or replacing domain expertise.

---

### 11.1 What ParetoMetaDecision Is Not

ParetoMetaDecision is **not**:

- A machine learning training framework  
- A black-box predictive model generator  
- An automated decision-maker acting without governance  
- A domain-specific solution tied to finance, healthcare, or any single field  

The framework does not aim to replace human judgment. Instead, it provides a structured environment to **analyze, optimize, and govern decision rules and policies**.

---

### 11.2 Relation to Machine Learning and Predictive Models

ParetoMetaDecision is **complementary** to machine learning.

- Predictive models can be:
  - Inputs to decision rules
  - Feature generators
  - Components within evaluators
- The framework does not optimize model weights or architectures.
- Its focus is on:
  - How predictions are used
  - When decisions are triggered
  - Which trade-offs are acceptable

In this sense, ParetoMetaDecision operates *downstream* of prediction, optimizing the **decision layer** rather than the learning layer.

---

### 11.3 Relation to Classical Decision Support Systems

Compared to traditional Decision Support Systems (DSS), ParetoMetaDecision introduces **explicit optimization and governance**.

- Classical DSS often rely on:
  - Static rules
  - Manual tuning
  - Single-objective criteria
- ParetoMetaDecision provides:
  - Multi-objective optimization
  - Explicit trade-off analysis
  - Reproducibility and auditability by construction

This positions the framework as an evolution of classical DSS toward **formally optimized and governed decision systems**.


## 12. Research and Publications

ParetoMetaDecision is developed with a **research-first mindset**, aiming to contribute to the scientific study of decision optimization, interpretability, and governance. The framework is designed to support reproducible research, rigorous experimentation, and publication in top-tier venues.

---

### 12.1 Academic Motivation

The primary academic motivation of ParetoMetaDecision is to address limitations of existing optimization and decision-support approaches.

- Decisions are treated as **first-class objects of optimization**, not as by-products of prediction.
- The framework focuses on:
  - Multi-objective trade-offs
  - Interpretability and decision complexity
  - Governance and reproducibility
- Emphasis is placed on **decision processes**, not only on final outcomes.

This positions ParetoMetaDecision within the research agenda of decision science, operational research, and responsible AI.

---

### 12.2 Target Journals and Research Context

The framework is aligned with research standards expected by **top-tier journals**.

- Core research areas include:
  - Multi-objective optimization
  - Decision support systems
  - Human-in-the-loop and governed decision-making
- Typical publication venues include:
  - Operations Research and Decision Sciences journals
  - Artificial Intelligence and Intelligent Systems journals
- Experimental design follows requirements for:
  - Reproducibility
  - Fair algorithmic comparison
  - Transparent evaluation

The framework is intended as both a research artifact and an experimental platform.

---

### 12.3 How to Cite ParetoMetaDecision

If you use ParetoMetaDecision in academic work, please cite it appropriately.

- Cite the relevant paper describing:
  - The decision optimization framework
  - The experimental setup and governance model
- Reference the software version or commit used in experiments.
- Include configuration and seed information when reporting results.

A citation template and BibTeX entry will be provided to ensure consistent and traceable referencing.


## 13. Getting Started

This section provides a concise and practical entry point to the framework. The objective is to enable users to run a **minimal, reproducible, and governed experiment** with minimal setup, while preserving all methodological guarantees.

---

### 13.1 Installation

ParetoMetaDecision is designed to be lightweight, explicit, and environment-agnostic.

- Clone the repository:
  ```bash
  git clone https://github.com/<org>/ParetoMetaDecision.git
  cd ParetoMetaDecision

### 13.2 Minimal Example

    pip install -r requirements.txt

    python main.py --config configs/example.yaml

### 13.3 Configuration Files (YAML)

    All experiments are driven by explicit, declarative YAML configuration files.

Configuration files specify:

Data sources and preprocessing steps

Decision representation and parameter space

Evaluation metrics and optimization objectives

Optimization strategy and governance constraints

YAML configurations are:

Human-readable

Version-controllable

Independent of implementation details

## 14. Project Structure

The repository is organized to clearly separate **core decision-optimization logic**, **governance and audit artifacts**, and **domain-specific extensions**. This structure is intentional and supports reproducibility, extensibility, and scientific clarity.

---

### 14.1 Repository Layout

At a high level, the project is structured as follows:

- `core/`  
  Framework kernel: decision language, optimization logic, governance, and evaluation semantics.

- `plugins/`  
  Domain-specific extensions defining data, problems, and evaluators.

- `config/`  
  Global system-level configuration.

- `data/`  
  Raw and immutable input datasets.

- `cache/`  
  Generated artifacts for auditability, reproducibility, and analysis.

- `tools/`  
  Auxiliary scripts for governance inspection and auditing.

- Top-level scripts and documents  
  Entry points, experiments, notebooks, and project documentation.

This separation ensures that **core logic is domain-agnostic**, while domain knowledge is isolated and replaceable.

---

### 14.2 Core Modules

The `core/` directory contains the foundational components of ParetoMetaDecision:

- `decision_language/`  
  Formal representation of decisions:
  - Abstract syntax tree (AST)
  - Constraints and registries
  - Language adapters

- `generation/`  
  Mechanisms for generating candidate decisions:
  - Combinatorial and guided discovery
  - Sentence and rule enumeration
  - Ledger for generated structures

- `optimizers/`  
  Optimization backends:
  - Grid, random, Bayesian, NSGA-II
  - Unified optimizer interface and registry

- `problem/`  
  Formal problem specification:
  - Parameter spaces
  - Objective definitions
  - Loader and registry mechanisms

- `governance/` and `contracts*`  
  Governance logic:
  - Decision scheduling
  - Validation contracts
  - Audit rules and enforcement

- `artifacts/`  
  Persistent logging of:
  - Decision events
  - Pattern discovery events
  - Hashing and artifact storage

- Supporting modules  
  Utilities for plotting, Pareto analysis, snapshots, tracking, and execution context.

Together, these modules implement a **governed, deterministic, and optimizer-independent decision optimization engine**.

---

### 14.3 Plugins and Domain Extensions

Domain-specific logic is implemented via the `plugins/` mechanism.

Each plugin typically defines:
- A `domain.yaml` describing the decision problem
- A `dataset.yaml` specifying data requirements
- A `data_loader.py` for domain-specific data access
- An `evaluator.py` implementing evaluation semantics
- A `problem_factory.py` binding the domain to the core framework
- Optional domain-specific policies or rules

Examples included in the repository:
- `plugins/inversionL2/`  
  Financial decision optimization using order flow and L2 market data.
- `plugins/patternDiscoveryL2/`  
  Pattern discovery and rule extraction in L2 data.

This design allows new domains to be added **without modifying the core**, preserving generality while enabling rich specialization.


## 15. Roadmap

This roadmap outlines the **planned evolution** of ParetoMetaDecision, balancing engineering improvements with open research challenges. The focus remains on **decision optimization, governance, and interpretability**, rather than model-centric learning.

---

### 15.1 Planned Features

Short- to mid-term development priorities include:

- **Extended governance mechanisms**
  - Richer audit artifacts and decision provenance
  - Explicit support for abstention and decision deferral policies
- **Advanced optimization control**
  - Adaptive search strategies across rounds
  - Hybrid optimization (e.g., grid → evolutionary refinement)
- **Enhanced interpretability metrics**
  - Formal complexity measures
  - Language-level simplification objectives
- **Scalability improvements**
  - Parallel evaluation support
  - Incremental and cached evaluations

These features aim to strengthen both research validity and practical usability.

---

### 15.2 Open Research Questions

Several research questions remain intentionally open:

- How should **decision abstention** be optimized alongside action selection?
- What are appropriate **objective functions for interpretability** across domains?
- How can governance constraints be dynamically adapted without biasing results?
- When does increased decision complexity cease to yield meaningful gains?

ParetoMetaDecision is designed as a platform to explore these questions experimentally.

---

### 15.3 Long-Term Vision

The long-term vision is to establish ParetoMetaDecision as a **general framework for governed decision optimization**.

- Decisions are optimized as explicit, auditable artifacts.
- Trade-offs between performance, risk, and interpretability are made visible.
- Human oversight is structurally embedded in the decision loop.

Ultimately, the framework aims to support **responsible, transparent, and scientifically grounded decision systems** across high-stakes domains.


## 16. License and Disclaimer

### 📝 License

ParetoMetaDecision is released under the **GNU General Public License v3.0 (GPL-3.0)**.

This license guarantees that:
- The software is free to use, study, modify, and redistribute.
- Any derivative work must remain under the same license terms.
- Source code availability is preserved for all redistributed versions.

The full license text is available in the `LICENSE` file at the root of the repository.

More details: [https://www.gnu.org/licenses/gpl-3.0.html](https://www.gnu.org/licenses/gpl-3.0.html)


---

### Disclaimer

This software is provided **“as is”**, without warranty of any kind, express or implied.

- ParetoMetaDecision is a **research and experimental framework**.
- It is not intended to provide automated or legally binding decisions.
- Results produced by the system must be interpreted and validated by qualified domain experts.

The authors assume no responsibility for decisions made or actions taken based on outputs generated by this software.



You can cite the software and refer to the exact version using a DOI (to be assigned via Zenodo).

---

## Documentation

The project documentation is available in the `docs/` directory.  
To consult the generated materials, simply navigate to that folder.

---

## 📖 Citation

Please cite this tool as:

> A. J. Hidalgo-Marín, A. J. Nebro, J. García-Nieto.  
> *ParetoMetaDecision: Governed multi-objective decision making with collaborative human–AI system, European Journal of Operational Research, 2026 (under review).

---

## 📬 Contact

For questions, feedback, or contributions:

- 📧 Email: [antonio.hidalgo@uma.es](mailto:antonio.hidalgo@uma.es)
- 📍 Institution: ITIS Software, University of Málaga

---

## 🙋‍♂️ Contributing

Pull requests are welcome! If you want to suggest improvements, fix bugs, or add new features, feel free to open an issue or submit a PR.
