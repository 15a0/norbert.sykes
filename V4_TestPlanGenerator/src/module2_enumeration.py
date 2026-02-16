#!/usr/bin/env python3
"""
Module 2: Branch-Aware Enumeration Engine (V4)

Replaces V3's random sampling with a three-phase approach:
    Phase 1: Branch-aware sampling (force gatekeeper values, sample within branches)
    Phase 2: Coverage check (identify uncovered questions)
    Phase 3: Z3 synthesis (ask Z3 to find assignments for uncovered questions)

This is the NEW module that makes V4 different from V3.
One-size-fits-all: works for both simple and complex forms.

Functions:
    enumerate_valid_assignments(model) - Main entry point
"""

from itertools import product
from collections import defaultdict
from z3 import *

from module3_validator import validate_assignment
from questionnaire_utils import extract_referenced_questions


# =============================================================================
# MODULE 2: BRANCH-AWARE ENUMERATION ENGINE
# =============================================================================

def enumerate_valid_assignments(model, max_per_branch=500):
    """
    Module 2: Enumerate valid test variable assignments using branch-aware strategy.
    
    Three-phase approach:
        Phase 1: Identify gatekeepers, force each value, sample within branches
        Phase 2: Check coverage - which questions are still uncovered?
        Phase 3: Use Z3 to synthesize assignments for uncovered questions
    
    Args:
        model: The model dict from build_z3_model()
        max_per_branch: Max combinations to try per gatekeeper branch
    
    Returns:
        List of valid assignments, each containing:
            - assignment: dict of {q_num: string_value}
            - visible_questions: list of visible question numbers
            - complete_assignment: dict of all test variable values
    """
    
    test_var_nums = model['test_variables']
    value_map = model['value_map']
    never_visible = model.get('never_visible', set())
    
    # Build valid test vars (same filtering as V3)
    valid_test_vars = {}
    excluded_test_vars = []
    
    for q_num in test_var_nums:
        if q_num in never_visible:
            excluded_test_vars.append(q_num)
            continue
        if q_num in value_map and value_map[q_num]:
            options = list(value_map[q_num].keys())
            if len(options) > 1:  # Must have more than just __NONE__
                valid_test_vars[q_num] = options
    
    if excluded_test_vars:
        print(f"  Excluding {len(excluded_test_vars)} never-visible test variables from enumeration")
        print()
    
    if not valid_test_vars:
        print("  No test variables with static options to enumerate")
        return []
    
    # =========================================================================
    # PHASE 1: Branch-Aware Sampling
    # =========================================================================
    print("  Phase 1: Branch-Aware Sampling")
    print("  " + "-" * 70)
    
    # Identify gatekeepers: variables that control the most other questions
    gatekeepers = identify_gatekeepers(model, valid_test_vars)
    
    if gatekeepers:
        print(f"  Identified {len(gatekeepers)} gatekeeper variable(s):")
        for gk_num, gk_info in gatekeepers.items():
            print(f"    Q{gk_num}: {gk_info['label']} (controls {gk_info['controlled_count']} questions)")
    else:
        print("  No gatekeepers identified - using standard enumeration")
    
    # Generate combinations using branch-aware strategy
    valid_assignments = branch_aware_enumerate(model, valid_test_vars, gatekeepers, max_per_branch)
    
    print(f"  Phase 1 result: {len(valid_assignments)} valid assignments found")
    print()
    
    # =========================================================================
    # PHASE 2: Coverage Check
    # =========================================================================
    print("  Phase 2: Coverage Check")
    print("  " + "-" * 70)
    
    # Determine which questions are covered
    all_covered = set()
    for va in valid_assignments:
        all_covered.update(va['visible_questions'])
    
    # Determine which questions should be covered (all non-hidden, non-never-visible)
    all_coverable = set()
    for q in model['questions']:
        if not q['hidden'] and q['number'] not in never_visible:
            all_coverable.append(q['number']) if hasattr(all_coverable, 'append') else all_coverable.add(q['number'])
    
    uncovered = all_coverable - all_covered
    
    if not uncovered:
        print(f"  100% coverage achieved! ({len(all_covered)} questions covered)")
        print()
        return valid_assignments
    
    print(f"  Coverage: {len(all_covered)}/{len(all_coverable)} questions")
    print(f"  Uncovered: {len(uncovered)} questions: {sorted(uncovered)}")
    print()
    
    # =========================================================================
    # PHASE 3: Z3 Synthesis (Cleanup)
    # =========================================================================
    print("  Phase 3: Z3 Synthesis (filling gaps)")
    print("  " + "-" * 70)
    
    synthesized = z3_synthesize_for_uncovered(model, valid_test_vars, uncovered)
    
    if synthesized:
        print(f"  Phase 3 result: {len(synthesized)} additional assignments synthesized")
        valid_assignments.extend(synthesized)
        
        # Recheck coverage
        all_covered = set()
        for va in valid_assignments:
            all_covered.update(va['visible_questions'])
        
        still_uncovered = all_coverable - all_covered
        if not still_uncovered:
            print(f"  100% coverage achieved after synthesis!")
        else:
            print(f"  Coverage after synthesis: {len(all_covered)}/{len(all_coverable)}")
            print(f"  Still uncovered: {len(still_uncovered)} questions: {sorted(still_uncovered)}")
    else:
        print(f"  Phase 3: No additional assignments could be synthesized")
    
    print()
    return valid_assignments


def identify_gatekeepers(model, valid_test_vars):
    """
    Identify gatekeeper variables - those that control the most other questions.
    
    Uses visibility condition references to count how many questions each
    test variable controls.
    
    Returns: dict of {q_num: {'label': str, 'controlled_count': int, 'options': list}}
    """
    from questionnaire_utils import extract_referenced_questions
    
    questions = model['questions']
    
    # Count how many questions each test variable controls
    control_count = defaultdict(set)
    
    for q in questions:
        if q['visibilityCondition'] is None:
            continue
        
        refs = extract_referenced_questions(q['visibilityCondition'])
        for ref in refs:
            ref_label = ref['question_label']
            for q2 in questions:
                if q2['label'] == ref_label and q2['number'] in valid_test_vars:
                    control_count[q2['number']].add(q['number'])
    
    # Select top 3 gatekeepers: variables that control at least 2 questions
    gatekeepers = {}
    count = 0
    for q_num, controlled in sorted(control_count.items(), key=lambda x: len(x[1]), reverse=True):
        if len(controlled) >= 2 and q_num in valid_test_vars:
            q = next(qx for qx in questions if qx['number'] == q_num)
            gatekeepers[q_num] = {
                'label': q['label'],
                'controlled_count': len(controlled),
                'options': valid_test_vars[q_num]
            }
            count += 1
            if count >= 3:
                break
    
    return gatekeepers


def branch_aware_enumerate(model, valid_test_vars, gatekeepers, max_per_branch):
    """
    Phase 1: Dependency-aware gatekeeper enumeration.
    
    For each gatekeeper, identify its visibility dependencies, then force
    gatekeeper + dependencies together. This avoids random sampling and
    guarantees all combos are valid.
    """
    import random
    
    valid_assignments = []
    total_tested = 0
    
    if not gatekeepers:
        # No gatekeepers - fall back to enumerating all test variables
        var_nums = sorted(valid_test_vars.keys())
        option_lists = []
        for q_num in var_nums:
            real_options = [opt for opt in valid_test_vars[q_num] if opt != '__NONE__']
            if not real_options:
                real_options = valid_test_vars[q_num]
            option_lists.append(real_options)
        
        total_combinations = 1
        for opts in option_lists:
            total_combinations *= len(opts)
        
        print(f"  No gatekeepers - enumerating all {total_combinations} combinations")
        all_combos = list(product(*option_lists))
        
        if len(all_combos) > max_per_branch:
            random.shuffle(all_combos)
            all_combos = all_combos[:max_per_branch]
            print(f"  Sampling {max_per_branch} of {total_combinations}")
        
        for combo in all_combos:
            assignment = {var_nums[i]: combo[i] for i in range(len(var_nums))}
            total_tested += 1
            is_valid, visible, complete, err = validate_assignment(assignment, model)
            if is_valid:
                valid_assignments.append({
                    'assignment': assignment,
                    'visible_questions': visible,
                    'complete_assignment': complete
                })
        
        print(f"  Tested {total_tested}, {len(valid_assignments)} valid")
        return valid_assignments
    
    # Identify dependencies for each gatekeeper
    gk_with_deps = {}
    for gk_num in sorted(gatekeepers.keys()):
        deps = identify_gatekeeper_dependencies(gk_num, model, valid_test_vars)
        gk_with_deps[gk_num] = deps
        print(f"  Q{gk_num} dependencies: {deps if deps else 'none (always visible)'}")
    
    # Build enumeration: for each gatekeeper, enumerate (gatekeeper + dependencies)
    print(f"  Enumerating gatekeeper + dependency combinations")
    
    for gk_num in sorted(gk_with_deps.keys()):
        deps = gk_with_deps[gk_num]
        
        # Variables to enumerate: gatekeeper + its dependencies
        enum_vars = [gk_num] + deps
        enum_var_nums = sorted(enum_vars)
        
        # Build option lists (real values only)
        option_lists = []
        for q_num in enum_var_nums:
            real_options = [opt for opt in valid_test_vars[q_num] if opt != '__NONE__']
            if not real_options:
                real_options = valid_test_vars[q_num]
            option_lists.append(real_options)
        
        # Generate combos for this gatekeeper
        all_combos = list(product(*option_lists))
        print(f"    Q{gk_num}: {len(all_combos)} combos (gatekeeper + {len(deps)} dependencies)")
        
        for combo in all_combos:
            assignment = {enum_var_nums[i]: combo[i] for i in range(len(enum_var_nums))}
            total_tested += 1
            
            is_valid, visible, complete, err = validate_assignment(assignment, model)
            if is_valid:
                valid_assignments.append({
                    'assignment': assignment,
                    'visible_questions': visible,
                    'complete_assignment': complete
                })
    
    print(f"  Tested {total_tested} gatekeeper+dependency combos, {len(valid_assignments)} valid")
    
    return valid_assignments


def identify_gatekeeper_dependencies(gk_num, model, valid_test_vars):
    """
    Identify which test variables a gatekeeper depends on for visibility.
    
    A gatekeeper depends on variable X if the gatekeeper is not visible when X is not set.
    """
    questions = model['questions']
    gk_q = next((q for q in questions if q['number'] == gk_num), None)
    
    if not gk_q or gk_q['visibilityCondition'] is None:
        return []  # No dependencies - always visible
    
    # Extract referenced question labels from visibility condition
    refs = extract_referenced_questions(gk_q['visibilityCondition'])
    
    # Find which test variables these references correspond to
    dependencies = []
    for ref in refs:
        ref_label = ref['question_label']
        for q in questions:
            if q['label'] == ref_label and q['number'] in valid_test_vars:
                if q['number'] not in dependencies:
                    dependencies.append(q['number'])
    
    return sorted(dependencies)


def z3_synthesize_for_uncovered(model, valid_test_vars, uncovered_questions):
    """
    Phase 3: Use Z3 to synthesize assignments that make uncovered questions visible.
    
    For each uncovered question, adds a constraint requiring that question to be visible,
    then asks Z3 to find a satisfying assignment.
    """
    
    synthesized = []
    already_synthesized_for = set()
    
    for q_num in sorted(uncovered_questions):
        if q_num in already_synthesized_for:
            continue
        
        # Check if this question has a visibility variable
        if q_num not in model['z3_visible']:
            continue
        
        # Create a solver with all base constraints + require this question visible
        solver = Solver()
        solver.add(model['constraints'])
        solver.add(model['z3_visible'][q_num] == True)
        
        result = solver.check()
        
        if result == sat:
            m = solver.model()
            
            # Extract the assignment from the Z3 model
            assignment = {}
            complete_assignment = {}
            visible_questions = []
            
            # Get test variable values
            for tv_num in model['test_variables']:
                if tv_num in model['z3_test_vars'] and tv_num in model['value_map'] and len(model['value_map'][tv_num]) > 1:
                    z3_val = m.evaluate(model['z3_test_vars'][tv_num])
                    int_val = z3_val.as_long()
                    
                    for string_val, encoded_val in model['value_map'][tv_num].items():
                        if encoded_val == int_val and string_val != '__NONE__':
                            assignment[tv_num] = string_val
                            complete_assignment[tv_num] = string_val
                            break
            
            # Get visible questions
            for vq_num in sorted(model['z3_visible'].keys()):
                vis = m.evaluate(model['z3_visible'][vq_num])
                if is_true(vis):
                    visible_questions.append(vq_num)
            
            synthesized.append({
                'assignment': assignment,
                'visible_questions': visible_questions,
                'complete_assignment': complete_assignment
            })
            
            # Mark all newly covered questions so we don't synthesize for them again
            for vq in visible_questions:
                already_synthesized_for.add(vq)
            
            print(f"    Synthesized assignment for Q{q_num} -> covers {len(visible_questions)} questions")
        
        elif result == unsat:
            print(f"    Q{q_num}: UNSATISFIABLE (impossible path)")
        else:
            print(f"    Q{q_num}: Z3 returned unknown")
    
    return synthesized
