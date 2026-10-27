"""
LTTB (Largest-Triangle-Three-Buckets) time-series downsampling algorithm.

Reference: Sveinn Steinarsson, "Downsampling Time Series for Visual Representation", 2013.
"""

from typing import List, Tuple
import math


def lttb_downsample(data: List[Tuple[float, float]], threshold: int) -> List[Tuple[float, float]]:
    """
    Downsample time-series data using the LTTB algorithm.

    Args:
        data: List of (x, y) tuples sorted by x, where x is typically a timestamp
              or days_since_start, and y is the measurement value.
        threshold: Target number of output points. Must be >= 2.

    Returns:
        Downsampled list of (x, y) tuples with length <= threshold.
    """
    data_length = len(data)

    if threshold >= data_length or threshold < 2:
        return data

    # Always keep first and last points
    sampled = [data[0]]

    # Bucket size (excluding first and last points)
    bucket_size = (data_length - 2) / (threshold - 2)

    a = 0  # Index of the previously selected point

    for i in range(1, threshold - 1):
        # Calculate the average point for the next bucket
        avg_range_start = int(math.floor((i + 1) * bucket_size)) + 1
        avg_range_end = int(math.floor((i + 2) * bucket_size)) + 1
        avg_range_end = min(avg_range_end, data_length)

        avg_x = 0.0
        avg_y = 0.0
        avg_range_length = avg_range_end - avg_range_start

        if avg_range_length == 0:
            avg_range_length = 1

        for j in range(avg_range_start, avg_range_end):
            avg_x += data[j][0]
            avg_y += data[j][1]

        avg_x /= avg_range_length
        avg_y /= avg_range_length

        # Get the range for this bucket
        range_start = int(math.floor(i * bucket_size)) + 1
        range_end = int(math.floor((i + 1) * bucket_size)) + 1
        range_end = min(range_end, data_length)

        # Find the point with the largest triangle area
        point_a_x = data[a][0]
        point_a_y = data[a][1]

        max_area = -1.0
        max_area_index = range_start

        for j in range(range_start, range_end):
            # Triangle area using cross product
            area = abs(
                (point_a_x - avg_x) * (data[j][1] - point_a_y)
                - (point_a_x - data[j][0]) * (avg_y - point_a_y)
            ) * 0.5

            if area > max_area:
                max_area = area
                max_area_index = j

        sampled.append(data[max_area_index])
        a = max_area_index

    # Always include the last point
    sampled.append(data[-1])

    return sampled


def lttb_downsample_dicts(
    data_points: List[dict],
    threshold: int,
    x_key: str = "days_since_start",
    y_key: str = "mean",
) -> List[dict]:
    """
    Convenience wrapper that accepts a list of dicts (as returned by the API)
    and returns a downsampled list of dicts, preserving all original fields.

    Args:
        data_points: List of dicts, each containing at least x_key and y_key.
        threshold: Target number of output points.
        x_key: Key for the x-axis value (default: "days_since_start").
        y_key: Key for the y-axis value (default: "mean").

    Returns:
        Downsampled list of dicts.
    """
    if threshold >= len(data_points) or threshold < 2:
        return data_points

    # Extract (x, y) tuples while keeping index mapping
    indexed_data = []
    for idx, dp in enumerate(data_points):
        x = dp.get(x_key)
        y = dp.get(y_key)
        if x is not None and y is not None:
            indexed_data.append((idx, float(x), float(y)))

    if len(indexed_data) <= threshold:
        return data_points

    # Run LTTB on (x, y) tuples
    xy_data = [(x, y) for _, x, y in indexed_data]
    sampled_xy = lttb_downsample(xy_data, threshold)

    # Build a set of selected (x, y) tuples for matching back
    sampled_set = set(sampled_xy)

    # Collect the original dicts in order
    result = []
    for idx, x, y in indexed_data:
        if (x, y) in sampled_set:
            result.append(data_points[idx])
            sampled_set.discard((x, y))
            if not sampled_set:
                break

    return result
