"""Time series downsampling utilities.

Provides algorithms for reducing the number of points in a time series
while preserving visual shape for charting purposes.
"""

from typing import Any, Sequence


def lttb_downsample(
    data: Sequence[tuple[Any, ...]],
    target_points: int,
    value_index: int = 1,
) -> list[tuple[Any, ...]]:
    """Largest-Triangle-Three-Buckets downsampling.

    Preserves the visual shape of time series while reducing the number
    of data points. This algorithm selects points that maintain the
    maximum visual fidelity for charting.

    Args:
        data: Sequence of (timestamp, value, ...) tuples
        target_points: Target number of output points (must be >= 2)
        value_index: Index of the value column in tuple (default: 1)

    Returns:
        Downsampled list of tuples

    Reference:
        Sveinn Steinarsson, "Downsampling Time Series for Visual Representation"
        https://skemman.is/handle/1946/15343

    Example:
        >>> data = [(0, 1.0), (1, 2.0), (2, 1.5), (3, 3.0), (4, 2.5)]
        >>> lttb_downsample(data, 3)
        [(0, 1.0), (3, 3.0), (4, 2.5)]
    """
    n = len(data)

    if n <= target_points or target_points < 2:
        return list(data)

    # Always keep first and last points
    result = [data[0]]

    # Calculate bucket size
    bucket_size = (n - 2) / (target_points - 2)

    a = 0  # Previous selected point index

    for i in range(target_points - 2):
        # Calculate bucket boundaries
        bucket_start = int((i + 1) * bucket_size) + 1
        bucket_end = int((i + 2) * bucket_size) + 1
        bucket_end = min(bucket_end, n - 1)

        # Calculate average point for next bucket
        next_bucket_start = bucket_end
        next_bucket_end = int((i + 3) * bucket_size) + 1
        next_bucket_end = min(next_bucket_end, n)

        if next_bucket_start >= next_bucket_end:
            next_bucket_end = next_bucket_start + 1

        avg_x = 0.0
        avg_y = 0.0
        avg_count = 0

        for j in range(next_bucket_start, min(next_bucket_end, n)):
            avg_x += data[j][0]
            avg_y += data[j][value_index]
            avg_count += 1

        if avg_count > 0:
            avg_x /= avg_count
            avg_y /= avg_count
        else:
            # Fall back to last point
            avg_x = data[-1][0]
            avg_y = data[-1][value_index]

        # Find point with largest triangle area in current bucket
        max_area = -1.0
        max_index = bucket_start

        point_a_x = data[a][0]
        point_a_y = data[a][value_index]

        for j in range(bucket_start, bucket_end):
            # Calculate triangle area using the shoelace formula
            # Area = 0.5 * |x1(y2-y3) + x2(y3-y1) + x3(y1-y2)|
            # Simplified for our three points: a, current, avg
            area = abs(
                (point_a_x - avg_x) * (data[j][value_index] - point_a_y)
                - (point_a_x - data[j][0]) * (avg_y - point_a_y)
            ) * 0.5

            if area > max_area:
                max_area = area
                max_index = j

        result.append(data[max_index])
        a = max_index

    # Always include last point
    result.append(data[-1])

    return result


def simple_downsample(
    data: Sequence[tuple[Any, ...]],
    target_points: int,
) -> list[tuple[Any, ...]]:
    """Simple interval-based downsampling.

    Selects points at regular intervals. Less accurate than LTTB
    but faster for very large datasets.

    Args:
        data: Sequence of tuples
        target_points: Target number of output points

    Returns:
        Downsampled list of tuples
    """
    n = len(data)

    if n <= target_points or target_points < 1:
        return list(data)

    step = n / target_points
    result = []

    for i in range(target_points):
        index = int(i * step)
        result.append(data[index])

    # Ensure last point is included
    if result[-1] != data[-1]:
        result[-1] = data[-1]

    return result


def min_max_downsample(
    data: Sequence[tuple[Any, ...]],
    target_points: int,
    value_index: int = 1,
) -> list[tuple[Any, ...]]:
    """Min-max downsampling for preserving peaks and troughs.

    Divides data into buckets and keeps both min and max from each.
    Good for preserving extremes in financial data.

    Args:
        data: Sequence of (timestamp, value, ...) tuples
        target_points: Target number of output points (will be even)
        value_index: Index of the value column in tuple

    Returns:
        Downsampled list of tuples (may have up to target_points * 2 points)
    """
    n = len(data)

    if n <= target_points or target_points < 2:
        return list(data)

    # Each bucket contributes 2 points (min and max)
    num_buckets = target_points // 2
    bucket_size = n / num_buckets

    result = []

    for i in range(num_buckets):
        bucket_start = int(i * bucket_size)
        bucket_end = int((i + 1) * bucket_size)
        bucket_end = min(bucket_end, n)

        if bucket_start >= bucket_end:
            continue

        bucket = data[bucket_start:bucket_end]

        min_point = min(bucket, key=lambda x: x[value_index])
        max_point = max(bucket, key=lambda x: x[value_index])

        # Add in timestamp order
        if min_point[0] <= max_point[0]:
            result.append(min_point)
            if min_point != max_point:
                result.append(max_point)
        else:
            result.append(max_point)
            if min_point != max_point:
                result.append(min_point)

    return result
