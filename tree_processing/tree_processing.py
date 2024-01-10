import pandas as pd
import json
import os
from pathlib import Path


def get_tree_structure(
    df,
    id_col='Functional Location',
    desc_col='Description of functional location',
    parent_id_col='Superior functional location',
    deletion_flag_col='System status',
    deletion_flag_value='DLFL',
    max_depth=12,
):
    """
    Processes a DataFrame representing a tree structure in adjacency list form and returns a new DataFrame with
    additional columns representing the hierarchy in materialized path and column stores. The new DataFrame will
    be in depth-first sorted order.

    Args:
        df (pd.DataFrame): Input DataFrame with primary key `id_col` where each row represents a node.
        id_col (str, optional): Column name for the primary key. Defaults to 'Functional Location'.
        desc_col (str, optional): Column name for the node description. Defaults to 'Description of functional location' (standard English SAP field).
        parent_id_col (str, optional): Column name for the parent ID (foreign key to the same table). Defaults to 'Superior functional location'.
        deletion_flag_col (str, optional): Column name for the deletion flag. Defaults to 'System Status'.
        deletion_flag_value (str, optional): Value indicating a deleted node. Defaults to 'DLFL'.
        max_depth (int, optional): Maximum depth of the tree. Defaults to 12.

    Returns:
        pd.DataFrame: A new DataFrame with additional columns representing the hierarchy in materialized path
        and column stores, sorted in depth-first order.
    """

    def get_level_id_and_level_desc(path_element, level):
        # Helper function
        # Each path element is a list of entry from tree_structure[id]['MaterialisedPathList'], ie they are lists of tuples containing the id and the description of the node.
        # Refer to the definition of tree_structure below
        # Returns strings that include the id and the description, separated by a hyphen
        if level >= len(path_element):
            return None, None
        id, desc = path_element[level]
        id_and_desc = f'{id} - {desc}'
        return id, id_and_desc

    def populate_dict_with_paths(record):
        # This is a helper function which is applied to each row of the dataframe to populate the tree structure.
        # This needs to be performed in sucessive iterations.
        # This returns True if changes were added to the tree structure (meaning another iteration needs to be performed to fully populate the dictionary)
        id = record[id_col]
        if id in tree_structure:
            return False  # Node has already been processed. No change
        desc = record[desc_col]
        path_element_tuple = (str(id), str(desc))
        parent_id = record[parent_id_col]
        deleted_node = record[deletion_flag_col] == deletion_flag_value
        if pd.isna(parent_id):
            # The node is a root node
            tree_structure[id] = {
                'MaterialisedPathList': [path_element_tuple],
                'IsInDeletedBranch': deleted_node,
            }
            return True  # A root node was added (this is a change)
        parent_node_data = tree_structure.get(parent_id)
        if parent_node_data:
            new_path = parent_node_data.get('MaterialisedPathList') + [
                path_element_tuple
            ]
            deleted_branch = deleted_node or parent_node_data.get('IsInDeletedBranch')
            tree_structure[id] = {
                'MaterialisedPathList': new_path,
                'IsInDeletedBranch': deleted_branch,
            }
            return True  # The node was added by adding to the data from the parent.
        return False  # Nothing changed

    # Make a copy of the input argument so as not to mutate it.
    df = df.copy()

    # Starting tree structure. This is only required to process datasets which do not contain a root node. If applied to a complete IH06 dataset, it can be changed to an empty dict.
    current_folder_path = Path(os.path.abspath(__file__)).parent
    try:
        # Private data, not part of the repository
        with open(
            current_folder_path / 'input' / 'starting_tree_structure.json', 'r'
        ) as file:
            tree_structure = json.load(file)
    except:
        with open(
            current_folder_path / 'input' / 'starting_tree_structure_example.json', 'r'
        ) as file:
            tree_structure = json.load(file)

    # This transforms the loaded data into a more complex data structure.
    updated_tree_structure = {}
    for paths in tree_structure:
        node_entry = {}
        materialsed_path_list = []
        for node in paths:
            node_tuple = list(node.items())[0]
            materialsed_path_list.append(node_tuple)
            node_id = node_tuple[0]
        updated_tree_structure[node_id] = node_entry
        node_entry['MaterialisedPathList'] = materialsed_path_list
        node_entry['IsInDeletedBranch'] = False
    tree_structure = updated_tree_structure

    # Start processing

    print('Building the dictionary of materialised paths. Iterations:')

    df[deletion_flag_col].astype(str)
    df['NumChildren'] = None
    df['Depth'] = None

    iteration_counter = 0
    while df.apply(populate_dict_with_paths, axis=1).any():
        iteration_counter += 1
        print(f'{iteration_counter}, ', end='')
        if iteration_counter > max_depth * 2:
            # Give up if all nodes cannot be processed after iterations exceeding twice the max depth. This would mean there are orphan nodes, or the tree is way too deep.
            # Orphan nodes will be represented as root nodes in the tree, but with the description changed to '(Orphan node)'.
            break
    print('done.')

    df['MaterialisedPathList'] = df[id_col].apply(
        lambda x: tree_structure.get(x, {}).get(
            'MaterialisedPathList', [(x, '(Orphan node)')]
        )
    )
    df['MaterialisedPath'] = df['MaterialisedPathList'].apply(
        lambda x: ' > '.join([id_temp for (id_temp, _) in x])
    )
    df['Depth'] = df['MaterialisedPathList'].apply(len) - 1

    # Sort the nodes in depth-first order
    print('Sorting the nodes in depth-first order')
    df = df.sort_values(by=['MaterialisedPath'])

    print('')
    print('Populating level columns:')

    def get_level_col_name(level):
        return f'L{level:02d}'

    def get_level_desc_col_name(level):
        return f'L{level:02d}_desc'

    for level in range(max_depth + 1):
        # Add blank columns. Added in bulk like this so the similar columns are adjacent.
        level_col_name = get_level_col_name(level)
        df[level_col_name] = None

    for level in range(max_depth + 1):
        # Add blank columns. Added in bulk like this so the similar columns are adjacent.
        level_desc_col_name = get_level_desc_col_name(level)
        df[level_desc_col_name] = None

    for level in range(max_depth + 1):
        level_col_name = get_level_col_name(level)
        level_desc_col_name = get_level_desc_col_name(level)

        print(f'{level_col_name}, {level_desc_col_name}, ', end='')
        df[level_col_name], df[level_desc_col_name] = zip(
            *df['MaterialisedPathList'].apply(
                lambda x: get_level_id_and_level_desc(x, level)
            )
        )

    print('done.')
    print('')
    print('Adding child counts')
    children_count = {}

    def add_child(row):
        parent_id = row[parent_id_col]
        children_count[parent_id] = children_count.get(parent_id, 0) + 1

    # Build the dictionary of children counts
    _ = df.apply(add_child, axis=1)

    # Lookup the children counts
    df['NumChildren'] = df[id_col].apply(lambda x: children_count.get(x, 0))

    df = df.drop(columns='MaterialisedPathList')
    total_nodes = len(df)
    print(f'Done processing {total_nodes} nodes.')
    return df


if __name__ == "__main__":
    current_folder_path = Path(os.path.abspath(__file__)).parent

    try:
        # Private data
        input_file_path = current_folder_path / 'input' / 'IH06.xlsx'
        df = pd.read_excel(input_file_path)
        output_file_path = current_folder_path / 'output' / 'IH01.xlsx'
    except:
        # Example data
        input_file_path = current_folder_path / 'input' / 'IH06_example.xlsx'
        df = pd.read_excel(input_file_path)
        output_file_path = current_folder_path / 'output' / 'IH01_example.xlsx'

    df_processed = get_tree_structure(df)

    print(f'Saving output file...')
    df_processed.to_excel(output_file_path, sheet_name='IH01')
    print(f'Complete')
