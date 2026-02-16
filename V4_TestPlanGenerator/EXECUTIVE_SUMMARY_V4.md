# V4 Test Plan Generator - Executive Summary

## The Business Problem

Organizations deploy complex digital forms and questionnaires to collect information from employees and customers. These forms often have conditional logic: questions appear or disappear based on user answers, creating thousands of possible paths through the form.

**The Challenge:**
- Manual testing of all possible paths is impractical (often millions of combinations)
- Incomplete testing leads to broken user experiences (missing questions, logic errors, data collection failures)
- Current approaches are either too slow (exhaustive testing) or too unreliable (random sampling)

## What Changed from V3 to V4

V3 used random sampling to generate test cases, then relied on Z3 to fill coverage gaps. This worked well for simpler forms but struggled with complex forms where conditional questions depend on other conditional questions (chained dependencies).

**V3's Limitation:** Random sampling often produced invalid test cases for forms with deep conditional chains, wasting cycles and sometimes failing to achieve full coverage.

**V4's Improvement:** Instead of random sampling, V4 uses a three-phase **dependency-aware enumeration** strategy:

1. **Phase 1 - Branch-Aware Sampling:** Identifies "gatekeeper" questions (questions whose answers control the visibility of many other questions) and systematically enumerates their valid combinations, respecting dependency chains. This produces valid test cases on the first try.
2. **Phase 2 - Coverage Check:** Verifies whether Phase 1 achieved 100% question coverage. If yes, no further work is needed.
3. **Phase 3 - Z3 Synthesis:** If gaps remain, the Z3 solver generates targeted test cases to cover the remaining questions.

**Result:** V4 achieves 100% coverage on 20 of 25 forms (80%), up from 18 of 25 (72%) in V3. The forms that V3 failed on due to complex dependency chains now succeed.

## How It Works (High Level)

1. **Analyze Form Logic** - Extract all conditional rules from the form definition
2. **Classify Questions** - Separate test variables (answers control other questions) from data collection questions (no downstream effect)
3. **Build Reverse Dependency Map** - For each question, identify what it controls and what controls it
4. **Translate to Z3 Constraints** - Convert visibility conditions into numeric constraints so the Z3 solver can reason about them
5. **Enumerate Valid Scenarios** - Systematically walk the dependency tree starting from gatekeeper questions, generating valid combinations
6. **Check Coverage** - Verify which questions are covered by enumerated scenarios
7. **Fill Gaps with Z3** - If coverage is incomplete, use Z3 to synthesize additional scenarios targeting uncovered questions
8. **Select Minimal Test Cases** - Use a greedy set cover algorithm to pick the smallest set of scenarios that cover all form behavior
9. **Deliver Test Plan** - Output actionable test cases with expected question visibility for each scenario

## The Technology: Z3 Solver

V4 leverages **Z3**, a proven constraint solver developed by Microsoft Research and used by major technology companies for software verification and security analysis.

### Why Z3?

- **Battle-tested:** Used in production by Microsoft, Google, and other enterprises for critical systems
- **Mathematically Sound:** Guarantees correctness of logical analysis
- **Efficient:** Optimized for complex constraint problems
- **Industry Standard:** De facto standard for formal verification

### What Z3 Does for Us

Instead of blindly testing random scenarios, Z3 **understands the form's logic** and:
- Validates that test scenarios are actually possible
- Identifies which questions will be visible in each scenario
- Finds contradictions and impossible conditions
- Ensures comprehensive coverage

### Example: Translating to Numeric Constraints

The form JSON says: Question 3 "What do you need?" has options "New List" and "Update a List". Question 5 "Desired name:" is visible when Q3 equals "New List".

**Human-readable:** `Q5 visible IF Q3 == "New List"`

**Z3 constraint:** We map the text options to numbers:
- "New List" → 1
- "Update a List" → 2
- (not answered / not visible) → 0

So the constraint becomes: `Q5_visible == (Q3 == 1)`

**Why numeric?** Z3 is a mathematical solver optimized for integer arithmetic. Numeric constraints solve in microseconds. String comparison would be orders of magnitude slower and introduce ambiguity (case sensitivity, whitespace, etc.).

### Example: Gap-Fill with Z3

After Phase 1 enumeration, suppose questions Q16, Q17, and Q18 haven't appeared in any test case yet.

**The problem:** Q16 is visible when `Q3 == 2 AND Q10 == 2`. Q17 is visible when `Q3 == 2 AND Q10 == 2`. Q18 is visible when `Q3 == 2 AND Q10 == 1`.

**Z3 synthesis:** "Find me a valid set of answers where at least one of these questions becomes visible."

**Z3 response:** "Set Q3 = 2 and Q10 = 2. That makes Q16 and Q17 visible." A new test case is generated, gap closed.

### Why Not Exhaustive Enumeration?

A fully exhaustive approach would enumerate every possible combination of every answer to every question. For a form with 10 test variables each having 3 options, that's 3^10 = 59,049 combinations. For 15 variables with 4 options each, that's 4^15 = over 1 billion combinations.

V4's approach is smarter: it only enumerates combinations of **gatekeeper** test variables and their dependencies. If a form has 2 gatekeepers with 3 options each, that's only 9 combinations to test—not billions. Most of those 9 will cover all reachable questions, making Phase 3 (Z3 gap-fill) unnecessary.

## Results: What We've Achieved

### Testing Scope
- **25 questionnaires** analyzed and tested
- **20 forms (80%)** achieved 100% test coverage
- **3 forms (12%)** achieved partial coverage due to form design constraints (excessive conditional complexity)
- **1 form (4%)** skipped (pure data collection, no conditional logic to test)
- **1 form (4%)** recognized as simple data collection (no test variables)

### Improvement Over V3
- **+2 forms** now at 100% coverage that V3 could not fully cover
- **Faster generation** - dependency-aware enumeration produces valid cases immediately, no wasted cycles
- **More predictable** - systematic enumeration vs. random sampling means consistent results every run

### Key Findings

**Success Stories:**
- Complex forms with 50+ questions and multiple conditional branches now have complete test coverage
- Forms with chained dependencies (question B depends on question A, question C depends on both A and B) are now handled correctly
- Test plan generation reduced from manual hours to automated seconds

**Design Insights:**
- 3 questionnaires revealed excessive conditional complexity that impacts both user experience and testability
- These forms have so many independent decision paths that comprehensive testing becomes impractical
- This feedback is valuable for form redesign and simplification

## Additional Tooling: Form Structure Index

V4 includes a standalone **Form Structure Index** tool that generates CSV reports for analyzing form architecture:

- **Question Index CSV** - Summary of every question: classification (test variable vs. data collection), what gates it, what it gates
- **Gating Relationships CSV** - Detailed view of every gating condition: which question controls which, with the exact operator and expected value

These CSVs include a questionnaire name column, enabling aggregation across all forms into a master dataset for cross-form analysis and reporting.

### Value of CSV Outputs

**Immediate Use Cases:**
- **Form Design Review** - Identify which questions are gatekeepers (control many others) vs. isolated questions
- **Complexity Analysis** - Spot forms with excessive conditional chains that impact user experience
- **Test Case Validation** - Verify that test cases cover all gating conditions
- **Stakeholder Communication** - Show non-technical stakeholders the form's conditional logic in tabular format

**Architectural Potential:**
- **Master Form Repository** - Aggregate CSVs from all 25 questionnaires into a single database or data warehouse
- **Cross-Form Pattern Detection** - Identify common gating patterns across forms (e.g., "which questions appear in 80% of our forms?")
- **Form Complexity Dashboard** - Build visualizations showing which forms are most complex, which questions are most critical
- **Regulatory Compliance** - Track which questions control sensitive data collection (e.g., "which questions gate PII fields?")
- **Form Redesign Guidance** - Use gating metrics to recommend simplification (e.g., "these 3 questions gate 50+ others—consider breaking into separate forms")
- **Question Reusability Analysis** - Find questions that appear in multiple forms and could be standardized
- **Dependency Graph Visualization** - Generate network diagrams showing how questions depend on each other

The CSV structure is intentionally flat and queryable—ready for import into Excel, Power BI, SQL databases, or custom analysis tools.

## Business Value

### Risk Reduction
- **Eliminates hidden bugs** in form logic before production deployment
- **Prevents data collection failures** from broken conditional logic
- **Reduces post-deployment support** costs from form issues

### Efficiency Gains
- **Automated test generation** replaces manual test case creation
- **Seconds vs. hours** for complex form validation
- **Scalable:** Same process works for 10-question and 100-question forms

### Design Improvement
- **Identifies over-complex forms** that should be simplified
- **Provides metrics** (coverage %) to guide form redesign
- **Validates form logic** before user deployment
- **Form Structure Index** enables cross-form analysis and pattern detection

## Architecture

V4 is built as a modular pipeline with clear separation of concerns:

| Module | Responsibility |
|--------|---------------|
| **questionnaire_utils.py** | Shared extraction and classification logic |
| **Module 1: Constraint Builder** | Converts form JSON into Z3 constraints |
| **Module 2: Enumerator** | Three-phase dependency-aware test case generation |
| **Module 3: Validator** | Validates generated test cases against Z3 model |
| **Module 4: Output Generator** | Produces human-readable test plans |
| **form_structure_index.py** | Standalone CSV reporting (bolt-on, does not affect core pipeline) |

## Proven Approach

This solution is built on:
- **Constraint solving:** Proven mathematical approach used in aerospace, automotive, and financial systems
- **Dependency-aware enumeration:** Systematic exploration of conditional branches, not random guessing
- **Greedy set cover:** Well-established optimization technique (independent of Z3) used in production systems worldwide
- **Comprehensive testing:** Validated against 25 real-world questionnaires

### About Greedy Set Cover

Greedy set cover is a separate algorithm from Z3, not part of it. Here's how it works:

**The problem:** After enumeration and gap-fill, we have 20 valid test cases. Each covers a different set of questions. We want the minimum number of test cases that together cover all questions.

**The greedy approach:**
1. Pick the test case that covers the most uncovered questions (e.g., test case #3 covers 15 questions)
2. Remove those 15 questions from the "uncovered" list
3. Pick the test case that covers the most of the remaining uncovered questions (e.g., test case #7 covers 8 more)
4. Repeat until all questions are covered

**Result:** 3 test cases instead of 20, same coverage. This is why we can deliver comprehensive test plans with minimal test cases.

## Conclusion

V4 Test Plan Generator improves on V3 by replacing random sampling with dependency-aware enumeration, achieving higher coverage rates and more predictable results. By leveraging proven constraint-solving technology and systematic branch exploration, we can now confidently validate complex forms and identify design improvements—delivering better user experiences and reducing operational risk.

**Status:** Production-ready and validated across 25 real-world questionnaires. 80% at full coverage, up from 72% in V3.
