import pandas as pd
import matplotlib.pyplot as plt

def read_variables_and_clauses_from_excel(file_path):
    """
    Read the number of variables and clauses from an Excel file.
    Assumes the file contains columns named 'Instance', 'Variables', and 'Total Clauses'.
    """
    df = pd.read_excel(file_path)
    return df[['Instance', 'Variables', 'Total Clauses']]

def plot_comparison_variables_and_clauses(file1, file2, output_image_variables, output_image_clauses):
    """
    Plot comparison of variables and clauses between two methods.
    """
    df1 = read_variables_and_clauses_from_excel(file1)
    df2 = read_variables_and_clauses_from_excel(file2)

    # Merge dataframes on 'Instance'
    merged_df = pd.merge(df1, df2, on='Instance', suffixes=('_file1', '_file2'))

    # Rename columns for clarity
    merged_df.rename(columns={
        'Variables_file1': 'Variables_File1',
        'Variables_file2': 'Variables_File2',
        'Total Clauses_file1': 'Clauses_File1',
        'Total Clauses_file2': 'Clauses_File2'
    }, inplace=True)

    # Plot variables comparison
    plt.figure(figsize=(12, 8))
    plt.plot(merged_df['Instance'], merged_df['Variables_File1'], label='Binomial', linestyle='-', marker='o')
    plt.plot(merged_df['Instance'], merged_df['Variables_File2'], label='Staircase', linestyle='--', marker='x')
    plt.xlabel('Instance')
    plt.ylabel('Number of Variables')
    plt.xticks(rotation=45, ha='right')
    plt.legend()
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.tight_layout()
    plt.savefig(output_image_variables)
    plt.savefig('statistic/' + output_image_variables.replace('.png', '.pdf'))
    plt.show()

    # Plot clauses comparison
    plt.figure(figsize=(12, 8))
    plt.plot(merged_df['Instance'], merged_df['Clauses_File1'], label='Binomial', linestyle='-', marker='o')
    plt.plot(merged_df['Instance'], merged_df['Clauses_File2'], label='Staircase', linestyle='--', marker='x')
    plt.xlabel('Instance')
    plt.ylabel('Number of Clauses')
    plt.xticks(rotation=45, ha='right')
    plt.legend()
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.tight_layout()
    plt.savefig(output_image_clauses)
    plt.savefig('statistic/' + output_image_clauses.replace('.png', '.pdf'))
    plt.show()

if __name__ == "__main__":
    # Input files
    file1 = 'statistic/output_binomial_optilog(best)_tt_open_wbo_intel.xlsx'
    file2 = 'statistic/output_sc_optilog(best)_tt_open_wbo_intel.xlsx'

    # Output images
    output_image_variables = 'comparison_variables.png'
    output_image_clauses = 'comparison_clauses.png'

    # Plot comparisons
    plot_comparison_variables_and_clauses(file1, file2, output_image_variables, output_image_clauses)