from helper import *

"""
scene_name: simple_tabletop_bottle_and_bowl
description: A transparent beverage bottle stands on the left side of a table,
and a white bowl rests on the right with a clear, collision-free gap.
"""


@register()
def tabletop_table() -> Shape:
    return library_call(
        "usd",
        oid="table_000",
        keywords=[
            "center_white_table",
            "table",
            "white",
            "rectangular",
            "support_surface",
            "center",
        ],
    )


@register()
def tabletop_left_bottle() -> Shape:
    return library_call(
        "usd",
        oid="benchmark_beverage_bottle_081",
        keywords=[
            "left_transparent_beverage_bottle",
            "beverage_bottle",
            "transparent",
            "plastic",
            "drink_container",
            "left",
        ],
    )


@register()
def tabletop_right_bowl() -> Shape:
    return library_call(
        "usd",
        oid="benchmark_bowl_004",
        keywords=[
            "right_white_bowl",
            "bowl",
            "white",
            "round",
            "tableware",
            "right",
        ],
    )


@register()
def simple_tabletop_bottle_and_bowl() -> Shape:
    table = library_call("tabletop_table")
    bottle = library_call("tabletop_left_bottle")
    bowl = library_call("tabletop_right_bowl")

    table_info = get_object_info(table)
    bottle_info = get_object_info(bottle)
    bowl_info = get_object_info(bowl)

    tabletop_z = table_info["max"][2]
    center_x = table_info["center"][0]
    center_y = table_info["center"][1]

    # Scene coordinates: +y is left and -y is right.
    # The table spans 1.0 m along y. At ±0.25 m, both footprints remain
    # inside its edges and their bounding boxes have a gap over 0.39 m.
    bottle_target = np.array([center_x, center_y + 0.25, tabletop_z])
    bowl_target = np.array([center_x, center_y - 0.25, tabletop_z])

    bottle = transform_shape(
        bottle,
        translation_matrix(
            (
                bottle_target[0] - bottle_info["center"][0],
                bottle_target[1] - bottle_info["center"][1],
                bottle_target[2] - bottle_info["min"][2],
            )
        ),
    )

    bowl = transform_shape(
        bowl,
        translation_matrix(
            (
                bowl_target[0] - bowl_info["center"][0],
                bowl_target[1] - bowl_info["center"][1],
                bowl_target[2] - bowl_info["min"][2],
            )
        ),
    )

    return concat_shapes(table, bottle, bowl)


@register()
def root_scene() -> Shape:
    return library_call("simple_tabletop_bottle_and_bowl")