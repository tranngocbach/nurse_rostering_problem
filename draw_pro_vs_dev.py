import pandas as pd
import matplotlib.pyplot as plt

def read_hard_soft_clauses_from_excel(file_path):
    df = pd.read_excel(file_path)
    return df[['Instance', 'Hard Clauses', 'Soft Clauses']]
def read_variables_from_excel(file_path):
    """
    Read the number of variables from an Excel file.
    Assumes the file contains a column named 'Instance' and 'Variables'.
    """
    df = pd.read_excel(file_path)
    return df[['Instance', 'Variables']]



def plot_hard_soft_clauses_comparison(file1, file2, output_image):
    df1 = read_hard_soft_clauses_from_excel(file1)
    df2 = read_hard_soft_clauses_from_excel(file2)

    # Merge dataframes on 'Instance'
    merged_df = pd.merge(df1, df2, on='Instance', suffixes=('_file1', '_file2'))

    # Rename columns for clarity
    merged_df.rename(columns={
        'Hard Clauses_file1': 'Hard Clauses_File1',
        'Soft Clauses_file1': 'Soft Clauses_File1',
        'Hard Clauses_file2': 'Hard Clauses_File2',
        'Soft Clauses_file2': 'Soft Clauses_File2'
    }, inplace=True)

    merged_df.rename(columns={
        'Hard Clauses For Proposed Method': 'Hard Clauses_File1',
        'Soft Clauses For Proposed Method': 'Soft Clauses_File1',
        'Hard Clauses For Developemental Method': 'Hard Clauses_File2',
        'Soft Clauses For Developemental Method': 'Soft Clauses_File2'
    }, inplace=True)

    # Plot the data
    plt.figure(figsize=(12, 8))
    plt.plot(merged_df['Instance'], merged_df['Hard Clauses_File1'], label='Hard Clauses (Proposed Method)', linestyle='-', marker='o')
    plt.plot(merged_df['Instance'], merged_df['Soft Clauses_File1'], label='Soft Clauses (Proposed Method)', linestyle='--', marker='x')
    plt.plot(merged_df['Instance'], merged_df['Hard Clauses_File2'], label='Hard Clauses (Developemental Method)', linestyle='-', marker='s')
    plt.plot(merged_df['Instance'], merged_df['Soft Clauses_File2'], label='Soft Clauses (Developemental Method)', linestyle='--', marker='d')

    plt.xlabel('Instance')
    plt.ylabel('Number of Clauses')
    # plt.title('Comparison of Hard and Soft Clauses')
    plt.xticks(rotation=45, ha='right')
    plt.legend()
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.tight_layout()

    # Save the plot as an image file
    plt.savefig(output_image)
    plt.savefig('statistic/' + output_image.replace('.png', '.pdf'))
    plt.show()

def plot_variable_comparison(file1, file2, output_image):
    """
    Compare the number of variables between two methods.
    """
    df1 = read_variables_from_excel(file1)
    df2 = read_variables_from_excel(file2)

    # Merge dataframes on 'Instance'
    merged_df = pd.merge(df1, df2, on='Instance', suffixes=('_file1', '_file2'))

    # Rename columns for clarity
    merged_df.rename(columns={
        'Variables_file1': 'Variables_File1',
        'Variables_file2': 'Variables_File2'
    }, inplace=True)

    # Plot the data
    plt.figure(figsize=(12, 8))
    plt.plot(merged_df['Instance'], merged_df['Variables_File1'], label='Variables (Proposed Method)', linestyle='-', marker='o')
    plt.plot(merged_df['Instance'], merged_df['Variables_File2'], label='Variables (Developmental Method)', linestyle='--', marker='x')

    plt.xlabel('Instance')
    plt.ylabel('Number of Variables')
    plt.xticks(rotation=45, ha='right')
    plt.legend()
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.tight_layout()

    # Save the plot as an image file
    plt.savefig(output_image)
    plt.savefig('statistic/' + output_image.replace('.png', '.pdf'))
    plt.show()


if __name__ == "__main__":
    file1 = 'statistic/output_sc_optilog(best)_tt_open_wbo_intel.xlsx'
    file2 = 'statistic/output_sc_new_optilog(best)_tt_open_wbo_intel.xlsx'

    # Plot hard and soft clauses comparison
    output_image_hard_soft_clauses = 'comparison_of_hard_soft_clauses.png'
    plot_hard_soft_clauses_comparison(file1, file2, output_image_hard_soft_clauses)

    output_image_variables = 'comparison_of_variables.png'
    plot_variable_comparison(file1, file2, output_image_variables)