import pathlib


def test_colab_badge_points_to_repo():
    readme = pathlib.Path(__file__).resolve().parents[1] / "README.md"
    content = readme.read_text()
    expected_link = "https://colab.research.google.com/github/ee-mvp/eejx/blob/main/examples/demo_notebook.ipynb"
    assert expected_link in content
