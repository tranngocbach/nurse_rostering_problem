import pandas as pd
import matplotlib.pyplot as plt


def read_variables_from_excel(file_path):
    df = pd.read_excel(file_path)
    return df[['Instance', 'Variables']]


def read_clauses_from_excel(file_path):
    df = pd.read_excel(file_path)
    return df[['Instance', 'Total Clauses']]


def plot_four_comparisons(file1, file2, file3, file4, output_image):
    df1 = read_variables_from_excel(file1)
    df2 = read_variables_from_excel(file2)
    df3 = read_variables_from_excel(file3)
    df4 = read_variables_from_excel(file4)

    # Merge dataframes on 'Instance'
    merged_df = pd.merge(df1, df2, on='Instance', suffixes=('_file1', '_file2'))
    merged_df = pd.merge(merged_df, df3, on='Instance')
    merged_df = pd.merge(merged_df, df4, on='Instance', suffixes=('_file3', '_file4'))

    # Rename columns for clarity
    merged_df.rename(columns={
        'Variables_file1': 'Variables_SC',
        'Variables_file2': 'Variables_Binomial',
        'Variables_file3': 'Variables_Third',
        'Variables_file4': 'Variables_Fourth'
    }, inplace=True)

    # Plot the data
    plt.figure(figsize=(12, 8))
    plt.plot(merged_df['Instance'], merged_df['Variables_SC'], label='Proposed with Binomial', linestyle='-', marker='o')
    plt.plot(merged_df['Instance'], merged_df['Variables_Binomial'], label='Developmental with Binomial', linestyle='--',marker='x')
    plt.plot(merged_df['Instance'], merged_df['Variables_Third'], label='Proposed with Staircase', linestyle='-',marker='s')
    plt.plot(merged_df['Instance'], merged_df['Variables_Fourth'], label='Developmental with Staircase', linestyle='--',marker='d')

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


def plot_four_comparisons_clauses(file1, file2, file3, file4, output_image):
    df1 = read_clauses_from_excel(file1)
    df2 = read_clauses_from_excel(file2)
    df3 = read_clauses_from_excel(file3)
    df4 = read_clauses_from_excel(file4)

    # Merge dataframes on 'Instance'
    merged_df = pd.merge(df1, df2, on='Instance', suffixes=('_file1', '_file2'))
    merged_df = pd.merge(merged_df, df3, on='Instance')
    merged_df = pd.merge(merged_df, df4, on='Instance', suffixes=('_file3', '_file4'))

    # Rename columns for clarity
    merged_df.rename(columns={
        'Total Clauses_file1': 'Clauses_SC',
        'Total Clauses_file2': 'Clauses_Binomial',
        'Total Clauses_file3': 'Clauses_Third',
        'Total Clauses_file4': 'Clauses_Fourth'
    }, inplace=True)

    # Plot the data
    plt.figure(figsize=(12, 8))
    plt.plot(merged_df['Instance'], merged_df['Clauses_SC'], label='Proposed with Binomial')
    plt.plot(merged_df['Instance'], merged_df['Clauses_Binomial'], label='Developmental with Binomial')
    plt.plot(merged_df['Instance'], merged_df['Clauses_Third'], label='Proposed with Staircase')
    plt.plot(merged_df['Instance'], merged_df['Clauses_Fourth'], label='Developmental with Staircase')

    plt.xlabel('Instance')
    plt.ylabel('Number of Total Clauses')
    plt.xticks(rotation=45, ha='right')
    plt.legend()
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.tight_layout()

    # Save the plot as an image file
    plt.savefig(output_image)
    plt.savefig('statistic/' + output_image.replace('.png', '.pdf'))
    plt.show()


if __name__ == "__main__":
    file1 = 'statistic/output_binomial_optilog(best)_tt_open_wbo_intel.xlsx'
    file2 = 'statistic/output_binomial_new_optilog(best)_tt_open_wbo_intel.xlsx'
    file3 = 'statistic/output_sc_optilog(best)_tt_open_wbo_intel.xlsx'
    file4 = 'statistic/output_sc_new_optilog(best)_tt_open_wbo_intel.xlsx'

    # Plot variables
    output_image_variables = 'comparison_of_four_variables.png'
    plot_four_comparisons(file1, file2, file3, file4, output_image_variables)

    # Plot clauses
    output_image_clauses = 'comparison_of_four_clauses.png'
    plot_four_comparisons_clauses(file1, file2, file3, file4, output_image_clauses)