import matplotlib.pyplot as plt
import contextily as ctx

def plot_walkscore_map(grid_gdf, city_name, score, save_path=None):
    # Generate a static map visualizing walkscores.

    # Create figure
    fig, ax = plt.subplots(figsize=(15, 15))

    # Plot walkscores
    grid_gdf.plot(
        column=score,
        ax=ax,
        cmap='viridis',
        legend=True,
        legend_kwds={
            'label': "Score (0-100)",
            'orientation': "horizontal"
        },
        alpha=0.7
    )

    # Add basemap
    ctx.add_basemap(
        ax,
        crs=grid_gdf.crs.to_string(),
        source=ctx.providers.CartoDB.Positron
    )

    # Set title and remove axis
    ax.set_title(f"Map: {city_name}", fontsize=16)
    ax.set_axis_off()

    # Save if path is provided
    if save_path:
        plt.savefig(save_path, bbox_inches='tight', dpi=300)

    return fig, ax


def plot_category_maps(grid_gdf, city_name, categories, base_column="poi_accessibility", save_dir="data/results"):
    # Generate maps for each POI category.
    import os

    # Create directory if it doesn't exist
    os.makedirs(save_dir, exist_ok=True)

    # Generate a map for each category
    for category in categories:
        column_name = f"{base_column}_{category}_score"

        if column_name not in grid_gdf.columns:
            print(f"Skipping category {category}: column {column_name} not found in data")
            continue

        # Create a copy of the grid with the category score as walkscore
        temp_gdf = grid_gdf.copy()
        temp_gdf["walkscore"] = temp_gdf[column_name]

        # Generate map
        title = f"{city_name} - {category.capitalize()} Accessibility"
        save_path = os.path.join(save_dir, f"{base_column}_{category}_map.png")

        # Call plot_walkscore_map with the correct parameters
        plot_walkscore_map(
            grid_gdf=temp_gdf,
            city_name=title,
            score="walkscore",
            save_path=save_path
        )