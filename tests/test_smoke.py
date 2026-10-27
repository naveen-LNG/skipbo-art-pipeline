import spine_qa


def test_scripts_importable():
    assert hasattr(spine_qa, "Rig")
