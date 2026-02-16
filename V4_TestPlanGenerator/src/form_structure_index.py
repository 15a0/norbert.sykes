#!/usr/bin/env python3
"""
Form Structure Index - Standalone Bolt-On Script

Generates CSV indexes of form gating relationships using the same
extraction logic that powers test plan generation (questionnaire_utils.py).

Outputs:
    <name>_gating_relationships.csv  - One row per gating relationship
    <name>_question_index.csv        - Summary of each question

All CSVs include Questionnaire_Name column for downstream aggregation.

Usage:
    python form_structure_index.py <questionnaire_json> [output_dir]
"""

import json
import sys
import os
import csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from questionnaire_utils import (
    extract_all_questions,
    build_reverse_dependency_map,
    classify_questions
)


def generate_gating_relationships_csv(questionnaire_name, questions, reverse_deps, classification, output_dir):
    """
    Generate CSV of all gating relationships.
    Each row: one parent question gates one child question, with the condition.
    """
    safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in questionnaire_name)
    csv_file = os.path.join(output_dir, f"{safe_name}_gating_relationships.csv")

    # Build a label-to-number map for parent questions
    label_to_num = {}
    for q in questions:
        label_to_num[q['label']] = q['number']

    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Questionnaire_Name',
            'Parent_Question_Number',
            'Parent_Question_Label',
            'Parent_Is_Test_Variable',
            'Child_Question_Number',
            'Child_Question_Label',
            'Operator',
            'Expected_Value'
        ])

        for parent_label, children in sorted(reverse_deps.items(), key=lambda x: label_to_num.get(x[0], 999)):
            parent_num = label_to_num.get(parent_label, '?')
            is_test_var = parent_num in classification['test_variables']

            for child in sorted(children, key=lambda x: x['child_number']):
                # Map operator to readable format
                op_map = {
                    'EQUALS': '==',
                    'NOT_EQUALS': '!=',
                    'CONTAINS': 'contains',
                    'NOT_CONTAINS': 'does not contain',
                    'INCLUDES': 'includes'
                }
                op_display = op_map.get(child['operator'], child['operator'])

                writer.writerow([
                    questionnaire_name,
                    f"Q{parent_num}",
                    parent_label,
                    'Yes' if is_test_var else 'No',
                    f"Q{child['child_number']}",
                    child['child_label'],
                    op_display,
                    child['expected_value'] or ''
                ])

    return csv_file


def generate_question_index_csv(questionnaire_name, questions, reverse_deps, classification, output_dir):
    """
    Generate CSV summary of each question.
    """
    safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in questionnaire_name)
    csv_file = os.path.join(output_dir, f"{safe_name}_question_index.csv")

    # Build a label-to-number map
    label_to_num = {}
    for q in questions:
        label_to_num[q['label']] = q['number']

    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Questionnaire_Name',
            'Question_Number',
            'Question_Label',
            'Type',
            'Classification',
            'Gated_By_Count',
            'Gated_By_Questions',
            'Gates_Count',
            'Gates_Questions'
        ])

        for q in sorted(questions, key=lambda x: x['number']):
            if q['hidden']:
                continue

            # Classification
            if q['number'] in classification['test_variables']:
                q_class = 'TEST_VAR'
            elif q['number'] in classification['data_collection']:
                q_class = 'DATA_COL'
            else:
                q_class = 'HIDDEN'

            # Gated by (from visibilityConditionRefs)
            gated_by = []
            for ref in q['visibilityConditionRefs']:
                parent_num = label_to_num.get(ref['question_label'], '?')
                gated_by.append(f"Q{parent_num}")
            gated_by = sorted(set(gated_by))

            # Gates (from reverse_deps)
            gates = []
            if q['label'] in reverse_deps:
                for child in reverse_deps[q['label']]:
                    gates.append(f"Q{child['child_number']}")
            gates = sorted(set(gates))

            writer.writerow([
                questionnaire_name,
                f"Q{q['number']}",
                q['label'],
                q['type'],
                q_class,
                len(gated_by),
                ', '.join(gated_by),
                len(gates),
                ', '.join(gates)
            ])

    return csv_file


def main():
    if len(sys.argv) < 2:
        print("Usage: python form_structure_index.py <questionnaire_json> [output_dir]")
        sys.exit(1)

    json_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    if not os.path.exists(json_file):
        print(f"Error: {json_file} not found")
        sys.exit(1)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Load questionnaire
    with open(json_file, 'r', encoding='utf-8') as f:
        questionnaire = json.load(f)

    questionnaire_name = questionnaire.get('name', 'questionnaire')
    questions = extract_all_questions(questionnaire)
    reverse_deps = build_reverse_dependency_map(questions)
    classification = classify_questions(questions, reverse_deps)

    print(f"Questionnaire: {questionnaire_name}")
    print(f"Total questions: {len(questions)}")
    print(f"Test variables: {len(classification['test_variables'])}")
    print(f"Data collection: {len(classification['data_collection'])}")
    print(f"Hidden: {len(classification['hidden'])}")
    print()

    # Generate CSVs
    rel_csv = generate_gating_relationships_csv(questionnaire_name, questions, reverse_deps, classification, output_dir)
    print(f"[OK] Gating relationships: {rel_csv}")

    idx_csv = generate_question_index_csv(questionnaire_name, questions, reverse_deps, classification, output_dir)
    print(f"[OK] Question index: {idx_csv}")


if __name__ == '__main__':
    main()
