import pandas as pd
import matplotlib.pyplot as plt


# def read_variables_from_excel(file_path):
#     df = pd.read_excel(file_path)
#     return df[['Instance', 'Variables']]


# def plot_comparison(file1, file2, output_image):
#     df1 = read_variables_from_excel(file1)
#     df2 = read_variables_from_excel(file2)

#     # Merge dataframes on 'Instance'
#     merged_df = pd.merge(df1, df2, on='Instance',
#                          suffixes=('_file1', '_file2'))

#     # Plot the data
#     plt.figure(figsize=(10, 6))
#     plt.plot(merged_df['Instance'],
#              merged_df['Variables_file1'], label='SC')
#     plt.plot(merged_df['Instance'],
#              merged_df['Variables_file2'], label='Binomial')

#     plt.xlabel('Instance')
#     plt.ylabel('Number of Hard Clauses')
#     # plt.title('Comparison of Number of Variables')
#     plt.xticks(rotation=45, ha='right')
#     plt.legend()
#     plt.grid(True, which='both', linestyle='--',
#              linewidth=0.5)  # Add grid lines
#     plt.tight_layout()

#     # Save the plot as an image file
#     # plt.savefig(output_image)
#     plt.savefig('statistic/' + output_image.replace('.png', '.pdf'))  # Save as PDF
#     plt.show()


def read_clauses_from_excel(file_path):
    df = pd.read_excel(file_path)
    df['Total Clauses'] = df['Hard Clauses'] + df['Soft Clauses']
    return df[['Instance', 'Total Clauses']]


def plot_comparison(file1, file2, output_image):
    df1 = read_clauses_from_excel(file1)
    df2 = read_clauses_from_excel(file2)

    # Merge dataframes on 'Instance'
    merged_df = pd.merge(df1, df2, on='Instance',
                         suffixes=('_file1', '_file2'))

    # Plot the data
    fig, ax = plt.subplots(figsize=(12, 6))

    bar_width = 0.35
    index = range(len(merged_df))

    bar1 = ax.bar(
        index, merged_df['Total Clauses_file1'], bar_width, label='SC')
    bar2 = ax.bar([i + bar_width for i in index],
                  merged_df['Total Clauses_file2'], bar_width, label='Binomial')

    ax.set_xlabel('Instance')
    ax.set_ylabel('Total Clauses')
    # ax.set_title('Comparison of Total Clauses')
    ax.set_xticks([i + bar_width / 2 for i in index])
    ax.set_xticklabels(merged_df['Instance'], rotation=45, ha='right')
    ax.legend()
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)

    plt.tight_layout()

    # Save the plot as an image file
    plt.savefig(output_image)
    # Save as PDF
    plt.savefig('statistic/' + output_image.replace('.png', '.pdf'))
    plt.show()


if __name__ == "__main__":
    file1 = 'statistic/output_for_SC.xlsx'
    file2 = 'statistic/new_output_for_binomial.xlsx'
    output_image = 'comparison_of_total_clauses.png'

    plot_comparison(file1, file2, output_image)
