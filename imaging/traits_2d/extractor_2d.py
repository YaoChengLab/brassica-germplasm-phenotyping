"""extractor_2d.py — copied 2D trait extractor.

A fixed copy of the trait extractor of the internal image-to-CSV pipeline (not released),
so trait extraction does not depend on a working copy that may change.

Source SHA256(first16): cde3c48565e45a96
Provides: PlantTraitExtractor2D (static methods extract_morphological /
          extract_color / extract_texture / extract_custom).
"""

"""
2D Plant Trait Extractors - Morphological, Color, and Texture Analysis

This module extracts various plant traits from binary masks and images.
Easily extensible - add new trait extraction methods as needed.
"""

import cv2
import numpy as np
from skimage.feature import graycoprops
from skimage.color import rgb2gray
from typing import Dict, List, Optional, Tuple


class PlantTraitExtractor2D:
    """
    Extract 2D plant traits from images and masks.

    Usage:
        extractor = PlantTraitExtractor2D()
        morph_traits = extractor.extract_morphological(image, mask, valid_contours)
        color_traits = extractor.extract_color(image, mask)
        texture_traits = extractor.extract_texture(image, mask)
    """

    # ==================== MORPHOLOGICAL TRAITS ====================

    @staticmethod
    def extract_morphological(image: np.ndarray, mask: np.ndarray,
                             valid_contours: List) -> Dict[str, float]:
        """
        Extract morphological traits from plant contours.

        Args:
            image: Input image (BGR)
            mask: Binary mask of plant
            valid_contours: List of valid contours

        Returns:
            Dictionary of morphological traits
        """
        traits = {}

        if not valid_contours:
            return traits

        # --- Basic Size Metrics ---
        area = sum(cv2.contourArea(c) for c in valid_contours)
        traits['area_pixels'] = area

        # Outer contour calculation
        main_outer_contour, perimeter, boundary_method = PlantTraitExtractor2D._get_robust_outer_contour(
            valid_contours, image.shape
        )
        traits['perimeter_pixels'] = perimeter if perimeter else 0
        traits['boundary_method'] = boundary_method

        # Convex hull metrics
        all_points = np.vstack(valid_contours)
        overall_convex_hull = cv2.convexHull(all_points)
        convex_hull_area = cv2.contourArea(overall_convex_hull)
        convex_hull_perimeter = cv2.arcLength(overall_convex_hull, True)

        traits['convex_hull_area_pixels'] = convex_hull_area
        traits['convex_hull_perimeter'] = convex_hull_perimeter

        # --- Shape Metrics ---
        # Solidity (Index 12): A / A_convex
        traits['solidity'] = area / convex_hull_area if convex_hull_area > 0 else None
        # Circularity 1/2 use the convex-hull (canopy-envelope) perimeter: a single
        # deterministic, temporally stable boundary. (The adaptive `perimeter` above
        # switched method by leaf spacing -> circularity jumped across a time series.
        # Note: this measures canopy-envelope roundness, NOT leaf-margin serration.)
        cp = convex_hull_perimeter
        # Circularity 1 (Index 5): P^2 / A
        traits['circularity_1'] = (cp ** 2) / area if cp and area > 0 else None
        # Circularity 2 (Index 6): 4*pi*A / P^2
        traits['circularity_2'] = (4 * np.pi * area) / (cp ** 2) if cp and cp > 0 else None

        # Bounding box metrics
        mask_uint8 = (mask > 0).astype(np.uint8)
        x, y, w, h = cv2.boundingRect(mask_uint8)
        bbox_area = w * h
        traits['plant_width'] = w
        traits['plant_height'] = h
        traits['bounding_box_area'] = bbox_area
        traits['extent'] = area / bbox_area if bbox_area > 0 else 0
        traits['equivalent_diameter'] = np.sqrt(4 * area / np.pi) if area > 0 else 0

        # --- Ellipse Fitting ---
        traits.update(PlantTraitExtractor2D._extract_ellipse_traits(all_points))

        # --- Eccentricity1 (Index 3): eigenvalue ratio lambda_min/lambda_max ---
        traits['eccentricity_eigenvalue_ratio'] = PlantTraitExtractor2D._eigenvalue_ratio(mask_uint8)

        # --- Radial Symmetry ---
        traits.update(PlantTraitExtractor2D._extract_radial_symmetry(mask_uint8, valid_contours))

        # --- Canopy Porosity (Index 20): 1 - A_plant / A_convex ---
        traits['canopy_porosity'] = 1 - (area / convex_hull_area) if convex_hull_area > 0 else 0

        # --- SIFT Features (Index 1) ---
        traits['sift_keypoint_count'] = PlantTraitExtractor2D._sift_keypoint_count(image, mask_uint8)

        # --- Multiscale Straightness of Boundaries (Index 21) ---
        traits['multiscale_straightness'] = PlantTraitExtractor2D._multiscale_straightness(main_outer_contour)

        # --- Combined Simple Connectivity (Index 22) ---
        traits['combined_simple_connectivity'] = PlantTraitExtractor2D._combined_simple_connectivity(mask_uint8)

        # --- Fuzzy Rule-Based Rectangularity (Index 24) ---
        traits['fuzzy_rectangularity'] = PlantTraitExtractor2D._fuzzy_rectangularity(main_outer_contour)

        return traits

    @staticmethod
    def _get_robust_outer_contour(valid_contours: List, img_shape: Tuple) -> Tuple[Optional[np.ndarray], Optional[float], str]:
        """Selects the best method to determine the plant's outer contour."""
        if not valid_contours:
            return None, 0, "no_valid_contours"

        # Analyze distances between leaf centroids
        centroids = []
        areas = []
        for contour in valid_contours:
            M = cv2.moments(contour)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                centroids.append(np.array([cx, cy]))
                areas.append(cv2.contourArea(contour))

        # Determine connectivity
        connectivity_ratio = 0
        if len(centroids) > 1:
            distances = [np.linalg.norm(c1 - c2) for i, c1 in enumerate(centroids) for c2 in centroids[i+1:]]
            min_distance = min(distances) if distances else 0
            mean_leaf_size = np.sqrt(np.mean(areas)) if np.mean(areas) > 0 else 1
            connectivity_ratio = min_distance / mean_leaf_size

        # Select method based on connectivity
        if connectivity_ratio < 3.0:
            method_used = "morphological_closing"
            main_outer_contour, perimeter = PlantTraitExtractor2D._morphological_method(valid_contours, img_shape)
        elif connectivity_ratio < 8.0:
            method_used = "adaptive_convex_hull"
            main_outer_contour, perimeter = PlantTraitExtractor2D._adaptive_convex_method(valid_contours, img_shape)
        else:
            method_used = "convex_hull"
            main_outer_contour, perimeter = PlantTraitExtractor2D._convex_hull_method(valid_contours)

        # Validate result quality
        if main_outer_contour is not None:
            outer_area = cv2.contourArea(main_outer_contour)
            total_leaf_area = sum(areas)
            area_ratio = outer_area / total_leaf_area if total_leaf_area > 0 else float('inf')

            if area_ratio > 6.0:
                main_outer_contour, perimeter = PlantTraitExtractor2D._convex_hull_method(valid_contours)
                method_used = "convex_hull_fallback"

        return main_outer_contour, perimeter, method_used

    @staticmethod
    def _morphological_method(valid_contours: List, img_shape: Tuple) -> Tuple[np.ndarray, float]:
        """Apply morphological closing to find outer contour."""
        temp_mask = np.zeros(img_shape[:2], dtype=np.uint8)
        cv2.drawContours(temp_mask, valid_contours, -1, 255, thickness=cv2.FILLED)
        total_area = sum(cv2.contourArea(c) for c in valid_contours)
        kernel_size = max(8, int(np.sqrt(total_area) * 0.1))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        closed_mask = cv2.morphologyEx(temp_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        dilated_mask = cv2.dilate(closed_mask, kernel, iterations=1)
        outer_contours, _ = cv2.findContours(dilated_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if outer_contours:
            main_outer_contour = max(outer_contours, key=cv2.contourArea)
            return main_outer_contour, cv2.arcLength(main_outer_contour, True)
        return PlantTraitExtractor2D._convex_hull_method(valid_contours)

    @staticmethod
    def _adaptive_convex_method(valid_contours: List, img_shape: Tuple) -> Tuple[np.ndarray, float]:
        """Apply adaptive convex hull method."""
        all_points = np.vstack(valid_contours)
        full_hull = cv2.convexHull(all_points)
        if cv2.contourArea(full_hull) > sum(cv2.contourArea(c) for c in valid_contours) * 3.0:
            alpha_contour, alpha_perimeter = PlantTraitExtractor2D._alpha_shape_approximation(valid_contours, img_shape)
            if alpha_contour is not None:
                return alpha_contour, alpha_perimeter
        return full_hull, cv2.arcLength(full_hull, True)

    @staticmethod
    def _alpha_shape_approximation(valid_contours: List, img_shape: Tuple) -> Tuple[Optional[np.ndarray], Optional[float]]:
        """Apply alpha shape approximation."""
        all_points = np.vstack(valid_contours).squeeze()
        temp_mask = np.zeros(img_shape[:2], dtype=np.uint8)
        for point in all_points:
            cv2.circle(temp_mask, tuple(point.astype(int)), 4, 255, -1)
        for kernel_size in [8, 15, 25, 35]:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
            dilated = cv2.dilate(temp_mask, kernel, iterations=1)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if len(contours) == 1:
                epsilon = 0.02 * cv2.arcLength(contours[0], True)
                smoothed_contour = cv2.approxPolyDP(contours[0], epsilon, True)
                return smoothed_contour, cv2.arcLength(smoothed_contour, True)
        return None, None

    @staticmethod
    def _convex_hull_method(valid_contours: List) -> Tuple[np.ndarray, float]:
        """Apply simple convex hull method."""
        all_points = np.vstack(valid_contours)
        hull = cv2.convexHull(all_points)
        return hull, cv2.arcLength(hull, True)

    @staticmethod
    def _extract_ellipse_traits(all_points: np.ndarray) -> Dict[str, float]:
        """Extract ellipse-based traits."""
        traits = {}
        if len(all_points) >= 5:
            try:
                ellipse = cv2.fitEllipse(all_points)
                axis1, axis2 = ellipse[1]
                major_axis = max(axis1, axis2)
                minor_axis = min(axis1, axis2)

                traits['major_axis_length'] = major_axis
                traits['minor_axis_length'] = minor_axis
                traits['ellipse_aspect_ratio'] = major_axis / minor_axis if minor_axis > 0 else float('inf')
                traits['ellipse_center_x'] = ellipse[0][0]
                traits['ellipse_center_y'] = ellipse[0][1]
                traits['ellipse_angle_degrees'] = ellipse[2]

                if major_axis > 0:
                    traits['eccentricity'] = np.sqrt(1 - (minor_axis ** 2) / (major_axis ** 2))
                else:
                    traits['eccentricity'] = 0
            except cv2.error:
                pass
        return traits

    @staticmethod
    def _extract_radial_symmetry(mask_uint8: np.ndarray, valid_contours: List) -> Dict[str, float]:
        """Extract radial symmetry and centroid-based traits."""
        traits = {}
        M = cv2.moments(mask_uint8)
        if M['m00'] > 0:
            cx = M['m10'] / M['m00']
            cy = M['m01'] / M['m00']

            radii = []
            for c in valid_contours:
                for point in c:
                    px, py = point[0]
                    radius = np.sqrt((px - cx) ** 2 + (py - cy) ** 2)
                    radii.append(radius)

            if radii:
                radii = np.array(radii)
                mean_radius = np.mean(radii)          # kept locally for radial_symmetry only
                std_radius = np.std(radii)
                traits['radial_symmetry'] = 1 - (std_radius / mean_radius) if mean_radius > 0 else 0
                # Radius-from-centroid: emit only std (contour irregularity, near size-
                # independent: r=0.26 vs equivalent_diameter) and min (nearest-point /
                # concavity, r=0.48, uncorrelated with max). Dropped max/mean/median —
                # they are ~size duplicates (mean≈median r=0.99; all r=0.8–0.94 with
                # equivalent_diameter) already covered by existing size traits.
                traits['std_radius_from_centroid'] = std_radius
                traits['min_radius_from_centroid'] = np.min(radii)
        return traits

    @staticmethod
    def _eigenvalue_ratio(mask_uint8: np.ndarray) -> float:
        """Eccentricity1 (Index 3): lambda_min / lambda_max of the covariance matrix
        of plant pixel coordinates. 1 = perfect circle, 0 = degenerate line."""
        ys, xs = np.where(mask_uint8 > 0)
        if len(xs) < 2:
            return 0.0
        coords = np.vstack([xs.astype(np.float64), ys.astype(np.float64)])
        cov = np.cov(coords)
        eigenvalues = np.linalg.eigvalsh(cov)
        eigenvalues = np.sort(np.abs(eigenvalues))
        if eigenvalues[-1] <= 0:
            return 0.0
        return float(eigenvalues[0] / eigenvalues[-1])

    @staticmethod
    def _sift_keypoint_count(image: np.ndarray, mask_uint8: np.ndarray) -> int:
        """Morphological #1: number of SIFT keypoints detected within the plant mask."""
        try:
            sift = cv2.SIFT_create()
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            keypoints = sift.detect(gray, mask=mask_uint8)
            return len(keypoints)
        except Exception:
            return 0

    @staticmethod
    def _multiscale_straightness(contour: Optional[np.ndarray]) -> float:
        """Morphological #21: max over scales s of n_s / (n-1), where n_s is the
        number of boundary pixels whose angle change at step s falls below
        a small threshold (i.e. nearly straight)."""
        if contour is None or len(contour) < 4:
            return 0.0
        pts = contour.reshape(-1, 2).astype(np.float64)
        n = len(pts)
        if n < 4:
            return 0.0
        angle_threshold = np.deg2rad(10)  # ~straight if direction change < 10 degrees
        max_straightness = 0.0
        # Multi-scale step sizes (relative to contour length)
        scales = sorted({max(1, int(round(n * f))) for f in (0.005, 0.01, 0.02, 0.05, 0.1)})
        for s in scales:
            if 2 * s >= n:
                continue
            v1 = pts[s:n - s] - pts[:n - 2 * s]
            v2 = pts[2 * s:] - pts[s:n - s]
            n1 = np.linalg.norm(v1, axis=1)
            n2 = np.linalg.norm(v2, axis=1)
            valid = (n1 > 0) & (n2 > 0)
            if not np.any(valid):
                continue
            cos_a = np.clip(np.einsum('ij,ij->i', v1[valid], v2[valid]) / (n1[valid] * n2[valid]), -1.0, 1.0)
            angles = np.arccos(cos_a)
            n_s = int(np.sum(angles < angle_threshold))
            straightness = n_s / max(1, n - 1)
            if straightness > max_straightness:
                max_straightness = straightness
        return float(min(1.0, max_straightness))

    @staticmethod
    def _combined_simple_connectivity(mask_uint8: np.ndarray) -> float:
        """Morphological #22: fuzzy AND (min) of two simple-connectivity terms:
        - PL_external / PL_total: external contour length over total contour length
        - A / A_filled: area before vs after hole-filling
        Sensitive to internal holes from lesions or insect damage."""
        # External contours
        ext_contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        # All contours including holes
        all_contours, _ = cv2.findContours(mask_uint8, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        if not ext_contours or not all_contours:
            return 0.0
        pl_ext = sum(cv2.arcLength(c, True) for c in ext_contours)
        pl_total = sum(cv2.arcLength(c, True) for c in all_contours)
        smpl_cnctvty = pl_ext / pl_total if pl_total > 0 else 0.0
        # Filled area = area inside external contours (no holes)
        area = float(np.sum(mask_uint8 > 0))
        filled = np.zeros_like(mask_uint8)
        cv2.drawContours(filled, ext_contours, -1, 255, thickness=cv2.FILLED)
        area_filled = float(np.sum(filled > 0))
        filled_area_ratio = area / area_filled if area_filled > 0 else 0.0
        return float(min(smpl_cnctvty, filled_area_ratio))

    @staticmethod
    def _fuzzy_rectangularity(contour: Optional[np.ndarray]) -> float:
        """Morphological #24: fuzzy rule-based rectangularity in [0, 1].
        Approximates contour with RDP, then evaluates how close the polygon
        is to a 4-corner rectangle via fuzzy membership functions on:
          (i) ~4 vertex angles near 90 degrees
          (ii) sufficient segment lengths between vertices
          (iii) at most 2 vertex angles deviate strongly from 90 degrees."""
        if contour is None or len(contour) < 4:
            return 0.0
        pts = contour.reshape(-1, 2).astype(np.float64)
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            return 0.0
        # RDP simplification
        approx = cv2.approxPolyDP(contour, epsilon=0.02 * perimeter, closed=True)
        v = approx.reshape(-1, 2).astype(np.float64)
        nv = len(v)
        if nv < 3:
            return 0.0
        # Compute interior angles at each vertex
        angles = []
        for i in range(nv):
            p_prev = v[(i - 1) % nv]
            p_cur = v[i]
            p_next = v[(i + 1) % nv]
            d1 = p_prev - p_cur
            d2 = p_next - p_cur
            n1 = np.linalg.norm(d1)
            n2 = np.linalg.norm(d2)
            if n1 == 0 or n2 == 0:
                continue
            cos_a = np.clip(np.dot(d1, d2) / (n1 * n2), -1.0, 1.0)
            angles.append(np.degrees(np.arccos(cos_a)))
        if not angles:
            return 0.0
        angles = np.array(angles)
        # Segment lengths (perimeter fraction)
        seg_lengths = np.array([np.linalg.norm(v[(i + 1) % nv] - v[i]) for i in range(nv)])
        seg_frac = seg_lengths / perimeter

        # Fuzzy membership for "angle near 90"
        # 1 at 90, decreases linearly to 0 at +-45 deg deviation
        deviation = np.abs(angles - 90)
        mu_angle90 = np.clip(1 - deviation / 45.0, 0, 1)
        # Fuzzy membership for "sufficient length" (segment >= 10% of perimeter -> 1, < 2% -> 0)
        mu_length = np.clip((seg_frac - 0.02) / (0.10 - 0.02), 0, 1)

        # Rule (i): ~4 corners with angle near 90 — count strong-membership vertices
        n_near90 = float(np.sum(mu_angle90 > 0.5))
        rule_i = max(0.0, 1 - abs(n_near90 - 4) / 4)
        # Rule (ii): mean length sufficiency for the top-4 strongest corners
        order = np.argsort(-mu_angle90)[:4]
        rule_ii = float(np.mean(mu_length[order])) if len(order) > 0 else 0.0
        # Rule (iii): <=2 vertices strongly deviate from 90
        n_deviant = float(np.sum(deviation > 30))
        rule_iii = max(0.0, 1 - max(0, n_deviant - 2) / max(1, nv))
        # Fuzzy AND across rules
        return float(min(rule_i, rule_ii, rule_iii))

    # ==================== COLOR TRAITS ====================

    @staticmethod
    def extract_color(image: np.ndarray, mask: np.ndarray) -> Dict[str, float]:
        """
        Extract color traits from plant region.

        Args:
            image: Input image (BGR)
            mask: Binary mask of plant

        Returns:
            Dictionary of color traits
        """
        mask = mask > 0
        if np.sum(mask) == 0:
            return {}

        traits = {}

        # Extract plant pixels
        plant_pixels_bgr = image[mask]
        plant_pixels_rgb = cv2.cvtColor(plant_pixels_bgr.reshape(-1, 1, 3), cv2.COLOR_BGR2RGB).reshape(-1, 3)

        r = plant_pixels_rgb[:, 0].astype(np.float64)
        g = plant_pixels_rgb[:, 1].astype(np.float64)
        b = plant_pixels_rgb[:, 2].astype(np.float64)

        mean_r = np.mean(r)
        mean_g = np.mean(g)
        mean_b = np.mean(b)
        rgb_sum = mean_r + mean_g + mean_b

        # === Basic RGB channels ===
        traits['red_channel'] = mean_r
        traits['green_channel'] = mean_g
        traits['blue_channel'] = mean_b

        # === Color Ratios (Index 1-3) ===
        traits['blue_green_ratio'] = mean_b / mean_g if mean_g > 0 else 0
        traits['red_green_ratio'] = mean_r / mean_g if mean_g > 0 else 0
        traits['blue_red_ratio'] = mean_b / mean_r if mean_r > 0 else 0

        # === HSV/HLS Color Space (Index 4-7) ===
        hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        plant_pixels_hsv = hsv_image[mask]
        mean_h_hsv = np.mean(plant_pixels_hsv[:, 0].astype(np.float64))
        mean_s_hsv = np.mean(plant_pixels_hsv[:, 1].astype(np.float64))  # for DGCI only
        mean_v_hsv = np.mean(plant_pixels_hsv[:, 2].astype(np.float64))  # for DGCI only

        # Hue (Index 4): from HSV (OpenCV gives 0-180)
        traits['hue'] = mean_h_hsv

        # Brightness (Index 5): sqrt((r^2 + g^2 + b^2) / 3)
        traits['brightness'] = np.mean(np.sqrt((r**2 + g**2 + b**2) / 3))

        # HLS color space (for Lightness #6 and Saturation #7)
        hls_image = cv2.cvtColor(image, cv2.COLOR_BGR2HLS)
        plant_pixels_hls = hls_image[mask]
        mean_l_hls = np.mean(plant_pixels_hls[:, 1].astype(np.float64))
        mean_s_hls = np.mean(plant_pixels_hls[:, 2].astype(np.float64))
        # Lightness (Index 6): (I_max + I_min) / 2 — HLS L
        traits['lightness'] = mean_l_hls
        # Saturation (Index 7): (I_max - I_min) / (2 - (I_max + I_min)) — HLS S
        traits['saturation'] = mean_s_hls

        # === Chroma & Anthocyanin Indices (Index 8-12) ===
        # Chroma (Index 8): (R - G) / ((R + G + B) / 3)
        rgb_mean = rgb_sum / 3
        traits['chroma'] = (mean_r - mean_g) / rgb_mean if rgb_mean > 0 else 0

        # Chroma' (Index 9): sqrt((R-G)^2 + (B-G)^2)
        traits['chroma_prime'] = np.sqrt((mean_r - mean_g)**2 + (mean_b - mean_g)**2)

        # Anthocyanin Content Chroma Difference (Index 10): (B+R)/2 - G
        traits['anthocyanin_chroma_difference'] = (mean_b + mean_r) / 2 - mean_g

        # Anthocyanin Content Chroma Ratio (Index 11): G / ((B+R)/2)
        br_half = (mean_b + mean_r) / 2
        traits['anthocyanin_chroma_ratio'] = mean_g / br_half if br_half > 0 else 0

        # Anthocyanin Content Chroma Basic (Index 12): (B+R) / G
        traits['anthocyanin_chroma_basic'] = (mean_b + mean_r) / mean_g if mean_g > 0 else 0

        # === Chromatic Coordinates / Strength (Index 13-15) ===
        # Strength of R/G/B == normalized chromatic coordinates r, g, b
        # Reused by TGI #25, MGRVI #27, RGBVI #28, CIVE #31, VEG #32
        r_chrom = mean_r / rgb_sum if rgb_sum > 0 else 0
        g_chrom = mean_g / rgb_sum if rgb_sum > 0 else 0
        b_chrom = mean_b / rgb_sum if rgb_sum > 0 else 0
        traits['strength_of_red'] = r_chrom
        traits['strength_of_green'] = g_chrom
        traits['strength_of_blue'] = b_chrom

        # === Vegetation Indices (Index 16-32) ===
        # Excess Green Index (Index 16): 2G - R - B
        traits['excess_green_index'] = 2 * mean_g - mean_r - mean_b

        # Excess Red Index (Index 17): 1.4R - G
        traits['excess_red_index'] = 1.4 * mean_r - mean_g

        # ExGR (Index 18): 3G - 2.4R - B
        traits['excess_green_minus_red'] = 3 * mean_g - 2.4 * mean_r - mean_b

        # Green Difference (Index 19): G - (R+B)/2
        traits['green_difference'] = mean_g - (mean_r + mean_b) / 2

        # Green Difference Variant (Index 20): (255 + G - (R+B)/2) / 2
        traits['green_difference_variant'] = (255 + mean_g - (mean_r + mean_b) / 2) / 2

        # Vegetation Index 2 (Index 21): (R-B) / (R+B)
        rb_sum = mean_r + mean_b
        traits['vegetation_index_2'] = (mean_r - mean_b) / rb_sum if rb_sum > 0 else 0

        # Green Leaf Index (Index 22): (2G-R-B) / (2G+R+B)
        num_gli = 2 * mean_g - mean_r - mean_b
        den_gli = 2 * mean_g + mean_r + mean_b
        traits['green_leaf_index'] = num_gli / den_gli if den_gli > 0 else 0

        # Greenness (Index 23): (2G-R-B) / (2R+G+B)
        den_greenness = 2 * mean_r + mean_g + mean_b
        traits['greenness'] = num_gli / den_greenness if den_greenness > 0 else 0

        # Green Index (Index 24): optimized RGB thresholds
        gi_r = (255 - abs(mean_r - 37.5)) / 255
        gi_g = (255 - abs(mean_g - 165)) / 255
        gi_b = (255 - abs(mean_b - 37.5)) / 255
        gi_mean = (gi_r + gi_g + gi_b) / 3
        traits['green_index'] = gi_mean / (12 * (1 - gi_mean)) if (1 - gi_mean) > 0 else 0

        # Triangular Greenness Index (Index 25): Rg - 0.39*Rr - 0.61*Rb
        # (uses chromatic coords from above)
        traits['triangular_greenness_index'] = g_chrom - 0.39 * r_chrom - 0.61 * b_chrom

        # NDYI (Index 26): (G-B) / (G+B)
        gb_sum = mean_g + mean_b
        traits['ndyi'] = (mean_g - mean_b) / gb_sum if gb_sum > 0 else 0

        # MGRVI (Index 27): (G^2 - R^2) / (G^2 + R^2)
        g2_r2_sum = mean_g**2 + mean_r**2
        traits['mgrvi'] = (mean_g**2 - mean_r**2) / g2_r2_sum if g2_r2_sum > 0 else 0

        # RGBVI (Index 28): (G^2 - B*R) / (G^2 + B*R)
        br_prod = mean_b * mean_r
        g2_br = mean_g**2 + br_prod
        traits['rgbvi'] = (mean_g**2 - br_prod) / g2_br if g2_br > 0 else 0

        # VARI (Index 29): (G-R) / (G+R-B)
        vari_den = mean_g + mean_r - mean_b
        traits['vari'] = (mean_g - mean_r) / vari_den if abs(vari_den) > 0 else 0

        # NGRDI (Index 30): (G-R) / (G+R)
        gr_sum = mean_g + mean_r
        traits['ngrdi'] = (mean_g - mean_r) / gr_sum if gr_sum > 0 else 0

        # CIVE (Index 31): 0.441r - 0.811g + 0.385b + 18.78745 (uses chromatic coords)
        traits['cive'] = 0.441 * r_chrom - 0.811 * g_chrom + 0.385 * b_chrom + 18.78745

        # VEG (Index 32): g / (r^0.667 * b^0.333)
        veg_den = (mean_r ** 0.667) * (mean_b ** 0.333) if mean_r > 0 and mean_b > 0 else 0
        traits['veg'] = mean_g / veg_den if veg_den > 0 else 0

        # DGCI (Index 33): ((Hue-60)/60 + (1-Sat) + (1-Brightness)) / 3
        # Use HSV values normalized to 0-1
        h_norm = mean_h_hsv * 2 / 360  # OpenCV hue is 0-180, convert to 0-1
        s_norm = mean_s_hsv / 255
        v_norm = mean_v_hsv / 255
        traits['dgci'] = ((h_norm * 360 - 60) / 60 + (1 - s_norm) + (1 - v_norm)) / 3

        # Number of Unique Colours (Index 34): unique RGB tuples whose pixel count > 10
        # (per Saric 2025 spec: count colours exceeding threshold of 10)
        _, color_counts = np.unique(plant_pixels_rgb, axis=0, return_counts=True)
        traits['num_unique_colours'] = int(np.sum(color_counts > 10))

        # Colour Distribution Modes (Index 35): number of "mean + 2*std" modes summed
        # over the R, G, B channel histograms. Faithful to saric2025 "RGB colour
        # distribution" (retains chromaticity). A single mean(R,G,B) intensity
        # histogram would discard colour and reduce this to a brightness measure.
        cdm = 0
        for _ch in range(3):  # plant_pixels_rgb is in R, G, B order
            _ch_hist, _ = np.histogram(plant_pixels_rgb[:, _ch], bins=256, range=(0, 255))
            _thr = _ch_hist.mean() + 2 * _ch_hist.std()
            cdm += int(np.sum(_ch_hist > _thr))
        traits['colour_distribution_modes'] = cdm

        # === RGB Channel Skewness (Index 36) & Kurtosis (Index 37) ===
        # Per-channel skewness and excess kurtosis for R, G, B, and Y (luma)
        y_luma = 0.299 * r + 0.587 * g + 0.114 * b  # ITU-R BT.601 luma
        for ch_name, ch_values in [('r', r), ('g', g), ('b', b), ('y', y_luma)]:
            traits[f'skewness_{ch_name}'] = PlantTraitExtractor2D._channel_skewness(ch_values)
            traits[f'kurtosis_{ch_name}'] = PlantTraitExtractor2D._channel_kurtosis(ch_values)

        return traits

    @staticmethod
    def _channel_skewness(x: np.ndarray) -> float:
        """Sample skewness: (1/n) * sum(((x - mean) / std)^3)."""
        if x.size < 2:
            return 0.0
        std = np.std(x)
        if std == 0:
            return 0.0
        return float(np.mean(((x - np.mean(x)) / std) ** 3))

    @staticmethod
    def _channel_kurtosis(x: np.ndarray) -> float:
        """Excess kurtosis: (1/n) * sum(((x - mean) / std)^4) - 3."""
        if x.size < 2:
            return 0.0
        std = np.std(x)
        if std == 0:
            return 0.0
        return float(np.mean(((x - np.mean(x)) / std) ** 4) - 3)

    # ==================== TEXTURE TRAITS ====================

    @staticmethod
    def _masked_glcm(patch_q: np.ndarray, patch_mask: np.ndarray, Ng: int,
                     distances: List[int], angles: List[float]) -> np.ndarray:
        """ROI-restricted GLCM: count co-occurrence pairs only where BOTH pixels
        fall inside patch_mask (background pairs excluded). Returns a float64 array
        shaped (Ng, Ng, len(distances), len(angles)), symmetric and normalized per
        (distance, angle) slice -- drop-in compatible with skimage.graycoprops.

        Fixes background dilution: feeding a whole bbox (background=0) into
        graycomatrix makes the (0,0) background pairs dominate every feature.
        """
        m = patch_mask.astype(bool)
        q = patch_q.astype(np.int64)
        H, W = q.shape
        glcm = np.zeros((Ng, Ng, len(distances), len(angles)), dtype=np.float64)
        for d_idx, d in enumerate(distances):
            for a_idx, ang in enumerate(angles):
                dr = int(round(np.sin(ang) * d))
                dc = int(round(np.cos(ang) * d))
                r0, r1 = max(0, -dr), min(H, H - dr)
                c0, c1 = max(0, -dc), min(W, W - dc)
                if r1 <= r0 or c1 <= c0:
                    continue
                src_v, src_m = q[r0:r1, c0:c1], m[r0:r1, c0:c1]
                dst_v = q[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
                dst_m = m[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
                both = src_m & dst_m
                if not np.any(both):
                    continue
                mat = np.bincount(src_v[both] * Ng + dst_v[both],
                                  minlength=Ng * Ng).reshape(Ng, Ng).astype(np.float64)
                mat = mat + mat.T                 # symmetric
                s = mat.sum()
                if s > 0:
                    mat /= s                       # normed per (distance, angle)
                glcm[:, :, d_idx, a_idx] = mat
        return glcm

    @staticmethod
    def extract_texture(image: np.ndarray, mask: np.ndarray) -> Dict[str, float]:
        """
        Extract texture traits from plant region.
        Includes GLCM features (Haralick 1973), pixel entropy, HoG, LoG,
        and spectral distribution modes.

        Args:
            image: Input image (BGR)
            mask: Binary mask of plant

        Returns:
            Dictionary of texture traits
        """
        mask = mask > 0
        if np.sum(mask) == 0:
            return {}

        gray_image = rgb2gray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        masked_gray = gray_image.copy()
        masked_gray[~mask] = 0
        masked_gray_uint8 = (masked_gray * 255).astype('uint8')

        rows, cols = np.where(mask)
        if len(rows) == 0:
            return {}

        row_min, row_max = rows.min(), rows.max()
        col_min, col_max = cols.min(), cols.max()
        patch = masked_gray_uint8[row_min:row_max+1, col_min:col_max+1]
        patch_mask = mask[row_min:row_max+1, col_min:col_max+1]

        traits = {}

        if patch.size == 0:
            return traits

        # === Pixel Entropy (Index 1) ===
        plant_pixels = masked_gray_uint8[mask]
        hist_pixel, _ = np.histogram(plant_pixels, bins=256, range=(0, 255))
        hist_pixel = hist_pixel / hist_pixel.sum()
        hist_pixel = hist_pixel[hist_pixel > 0]
        traits['pixel_entropy'] = -np.sum(hist_pixel * np.log2(hist_pixel))

        # === HoG (Index 2) ===
        from skimage.feature import hog
        patch_resized = cv2.resize(patch, (128, 128))
        hog_features = hog(patch_resized, orientations=9, pixels_per_cell=(16, 16),
                          cells_per_block=(2, 2), feature_vector=True)
        traits['hog_mean'] = np.mean(hog_features)
        traits['hog_std'] = np.std(hog_features)

        # === LoG (Index 3) ===
        log_response = cv2.GaussianBlur(patch.astype(np.float64), (0, 0), 2)
        log_response = cv2.Laplacian(log_response, cv2.CV_64F)
        log_masked = log_response[patch_mask]
        traits['log_mean'] = np.mean(log_masked) if len(log_masked) > 0 else 0
        traits['log_std'] = np.std(log_masked) if len(log_masked) > 0 else 0

        # === GLCM Features (Index 4-25) ===
        # Quantize to 64 levels for performance
        Ng = 64
        patch_q = (patch // 4).astype(np.uint8)

        distances = [1]
        angles = [0, np.pi/4, np.pi/2, 3*np.pi/4]
        glcm = PlantTraitExtractor2D._masked_glcm(patch_q, patch_mask, Ng,
                                                  distances, angles)

        # skimage built-in properties (averaged across angles)
        # ASM (Index 4): sum of p(i,j)^2; skimage 'energy' = sqrt(ASM), so ASM = energy^2
        traits['glcm_asm'] = float(np.mean(graycoprops(glcm, 'energy') ** 2))
        traits['glcm_contrast'] = np.mean(graycoprops(glcm, 'contrast'))
        traits['glcm_correlation'] = np.mean(graycoprops(glcm, 'correlation'))
        traits['glcm_idm'] = np.mean(graycoprops(glcm, 'homogeneity'))
        traits['glcm_dissimilarity'] = np.mean(graycoprops(glcm, 'dissimilarity'))

        # Average GLCM across angles for manual features
        glcm_2d = np.mean(glcm[:, :, 0, :], axis=2)

        # Precompute index grids (vectorized)
        i_idx = np.arange(Ng, dtype=np.float64).reshape(-1, 1)
        j_idx = np.arange(Ng, dtype=np.float64).reshape(1, -1)
        diff_ij = np.abs(i_idx - j_idx)

        # Marginal distributions
        px = np.sum(glcm_2d, axis=1)
        py = np.sum(glcm_2d, axis=0)
        mu_x = np.sum(np.arange(Ng, dtype=np.float64) * px)
        mu_y = np.sum(np.arange(Ng, dtype=np.float64) * py)

        # p_{x+y} and p_{x-y} (vectorized)
        p_xpy = np.zeros(2 * Ng - 1)
        p_xmy = np.zeros(Ng)
        for k in range(2 * Ng - 1):
            mask_k = (i_idx + j_idx) == k
            p_xpy[k] = np.sum(glcm_2d[mask_k])
        for k in range(Ng):
            mask_k = diff_ij == k
            p_xmy[k] = np.sum(glcm_2d[mask_k])

        # SSV (Index 8)
        traits['glcm_ssv'] = float(np.sum(((i_idx - mu_x) ** 2) * glcm_2d))

        # Sum Average (Index 9)
        k_arr = np.arange(2 * Ng - 1, dtype=np.float64)
        traits['glcm_sum_average'] = float(np.sum(k_arr * p_xpy))

        # Sum Entropy (Index 11)
        p_xpy_nz = p_xpy[p_xpy > 0]
        sum_entropy = float(-np.sum(p_xpy_nz * np.log2(p_xpy_nz)))
        traits['glcm_sum_entropy'] = sum_entropy

        # Sum Variance (Index 10)
        traits['glcm_sum_variance'] = float(np.sum(((k_arr - sum_entropy) ** 2) * p_xpy))

        # Entropy (Index 12)
        glcm_nz = glcm_2d[glcm_2d > 0]
        traits['glcm_entropy'] = float(-np.sum(glcm_nz * np.log2(glcm_nz)))

        # Difference Variance (Index 13): variance of the p_{x-y} distribution
        # = sum_k (k - mu)^2 * p_{x-y}(k), where mu = sum_k k * p_{x-y}(k)
        k_arr_xmy = np.arange(Ng, dtype=np.float64)
        mu_xmy = np.sum(k_arr_xmy * p_xmy)
        traits['glcm_difference_variance'] = float(np.sum(((k_arr_xmy - mu_xmy) ** 2) * p_xmy))

        # Difference Entropy (Index 14)
        p_xmy_nz = p_xmy[p_xmy > 0]
        traits['glcm_difference_entropy'] = float(-np.sum(p_xmy_nz * np.log2(p_xmy_nz)))

        # Inverse Difference (Index 15) - vectorized
        traits['glcm_inverse_difference'] = float(np.sum(glcm_2d / (1 + diff_ij)))

        # Autocorrelation (Index 17)
        traits['glcm_autocorrelation'] = float(np.sum(i_idx * j_idx * glcm_2d))

        # Cluster Shade (Index 18) & Cluster Prominence (Index 19)
        ij_mu = i_idx + j_idx - mu_x - mu_y
        traits['glcm_cluster_shade'] = float(np.sum((ij_mu ** 3) * glcm_2d))
        traits['glcm_cluster_prominence'] = float(np.sum((ij_mu ** 4) * glcm_2d))

        # Maximum Probability (Index 20)
        traits['glcm_max_probability'] = float(np.max(glcm_2d))

        # IMC1 & IMC2 (Index 21-22) - vectorized
        eps = 1e-15
        hxy = traits['glcm_entropy']
        px_mat = px.reshape(-1, 1)
        py_mat = py.reshape(1, -1)
        pxpy = px_mat * py_mat

        nz_mask = glcm_2d > 0
        hxy1 = -float(np.sum(glcm_2d[nz_mask] * np.log2(pxpy[nz_mask] + eps)))
        hx = -float(np.sum(px[px > 0] * np.log2(px[px > 0])))
        hy = -float(np.sum(py[py > 0] * np.log2(py[py > 0])))
        max_hxy = max(hx, hy)
        traits['glcm_imc1'] = (hxy - hxy1) / max_hxy if max_hxy > 0 else 0

        pxpy_nz = pxpy[pxpy > 0]
        hxy2 = -float(np.sum(pxpy_nz * np.log2(pxpy_nz + eps)))
        imc2_val = 1 - np.exp(-2.0 * (hxy2 - hxy))
        traits['glcm_imc2'] = float(np.sqrt(max(0, imc2_val)))

        # MCC (Index 23) - vectorized Q matrix
        try:
            px_safe = px.copy()
            px_safe[px_safe == 0] = 1
            py_safe = py.copy()
            py_safe[py_safe == 0] = 1
            # Q[i,j] = sum_k (P[i,k]*P[j,k]) / (px[i]*py[k])
            P_over_py = glcm_2d / py_safe.reshape(1, -1)
            Q = (glcm_2d @ P_over_py.T) / px_safe.reshape(-1, 1)
            eigenvalues = np.sort(np.real(np.linalg.eigvals(Q)))
            traits['glcm_mcc'] = float(np.sqrt(max(0, eigenvalues[-2])))
        except Exception:
            traits['glcm_mcc'] = 0.0

        # IDN (Index 24) - vectorized
        traits['glcm_idn'] = float(np.sum(glcm_2d / (1 + diff_ij / Ng)))

        # IDMN (Index 25) - vectorized
        traits['glcm_idmn'] = float(np.sum(glcm_2d / (1 + (diff_ij ** 2) / (Ng ** 2))))

        # === Spectral Distribution Modes (Index 26) ===
        f_transform = np.fft.fft2(patch.astype(np.float64))
        f_shift = np.fft.fftshift(f_transform)
        magnitude = np.abs(f_shift).flatten()
        mag_mean = np.mean(magnitude)
        mag_std = np.std(magnitude)
        threshold = mag_mean + 2 * mag_std
        traits['spectral_distribution_modes'] = int(np.sum(magnitude > threshold))

        return traits

    # ==================== CUSTOM TRAITS (Add new traits here!) ====================

    @staticmethod
    def extract_custom(image: np.ndarray, mask: np.ndarray,
                      valid_contours: List, **kwargs) -> Dict[str, float]:
        """
        Extract custom plant traits.

        Add your new trait extraction methods here!
        This is the place to extend the extractor with new traits.

        Args:
            image: Input image (BGR)
            mask: Binary mask of plant
            valid_contours: List of valid contours
            **kwargs: Additional parameters

        Returns:
            Dictionary of custom traits
        """
        traits = {}

        # Example: Add your custom traits below
        # traits['my_custom_trait_1'] = calculate_something(image, mask)
        # traits['my_custom_trait_2'] = calculate_something_else(valid_contours)

        return traits
