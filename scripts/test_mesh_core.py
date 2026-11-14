"""Deterministic tests of alignment and association failure-prone cases."""
import unittest
import numpy as np

from mesh_core import FaceAssociator, match_time, transform_xy


def detection(x, y=0.4):
    angles = np.linspace(0, 2 * np.pi, 478, endpoint=False)
    points = np.column_stack((x + .05 * np.cos(angles), y + .07 * np.sin(angles), np.zeros(478)))
    return {"raw_landmarks": points.tolist()}


class AlignmentTests(unittest.TestCase):
    def test_missing_frames_prefer_earlier_tie(self):
        self.assertEqual(match_time([0, 1 / 30, 3 / 30, 4 / 30], 2 / 30), 1)
        self.assertEqual(match_time([0, 1 / 30, 3 / 30, 4 / 30], 3 / 30), 2)

    def test_large_or_empty_time_gap_rejected(self):
        with self.assertRaises(ValueError):
            match_time([0, 1], .5)
        with self.assertRaises(ValueError):
            match_time([], 0)

    def test_scale_and_explicit_mirror(self):
        points = [[.2, .3, -.02], [.8, .7, .02]]
        np.testing.assert_array_equal(transform_xy(points, [[1, 0, 0], [0, 1, 0]], 720, 1280), [[144, 384], [576, 896]])
        np.testing.assert_array_equal(transform_xy(points, [[-1, 0, 1], [0, 1, 0]], 720, 1280), [[576, 384], [144, 896]])

    def test_crop_padding_transform_and_invalid_values(self):
        np.testing.assert_array_equal(transform_xy([[.5, .5]], [[2, 0, -.5], [0, .5, .25]], 100, 200), [[50, 100]])
        with self.assertRaises(ValueError):
            transform_xy([[float("nan"), .5]], [[1, 0, 0], [0, 1, 0]], 100, 200)


class AssociationTests(unittest.TestCase):
    def test_result_order_does_not_define_track_identity(self):
        tracker = FaceAssociator(smoothing_ms=0)
        initial = tracker.update([detection(.2), detection(.8)], 0)
        later = tracker.update([detection(.79), detection(.21)], 1 / 30)
        self.assertEqual([face['track_id'] for face in later], [initial[1]['track_id'], initial[0]['track_id']])

    def test_no_frozen_face_and_long_gap_creates_new_track(self):
        tracker = FaceAssociator()
        first_id = tracker.update([detection(.5)], 0)[0]['track_id']
        self.assertEqual(tracker.update([], 1 / 30), [])
        later = tracker.update([detection(.5)], 1)[0]
        self.assertNotEqual(first_id, later['track_id'])
        self.assertFalse(later['smoothed'])

    def test_cut_reset_drops_filter_history(self):
        tracker = FaceAssociator()
        first = tracker.update([detection(.5)], 0)[0]
        tracker.reset()
        later = tracker.update([detection(.5)], 1 / 30)[0]
        self.assertNotEqual(first['track_id'], later['track_id'])
        self.assertFalse(later['smoothed'])

    def test_ambiguous_assignment_is_flagged(self):
        tracker = FaceAssociator()
        tracker.update([detection(.4), detection(.42)], 0)
        later = tracker.update([detection(.41)], 1 / 30)[0]
        self.assertTrue(later['association_ambiguous'])
        self.assertFalse(later['smoothed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
