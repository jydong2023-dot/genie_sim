from helper import *

"""
scene_name: simple_table_with_bottle_and_bowl
description: A transparent beverage bottle stands on the left side of a table,
while a white bowl rests on the right side with a clear gap between them.
"""


@register()
def tabletop_objects() -> Shape:
    # In the scene coordinate system, +y is left and -y is right.
    bottle = library_call(
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
    bowl = library_call(
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

    # Their origins are normalized to their bottoms by usd(), so z=0 places
    # both objects directly on the receiving surface.
    bottle = transform_shape(
        bottle,
        translation_matrix((0.0, 0.22, 0.0)),
    )
    bowl = transform_shape(
        bowl,
        translation_matrix((0.0, -0.22, 0.0)),
    )

    return concat_shapes(bottle, bowl)


@register()
def simple_table_with_bottle_and_bowl() -> Shape:
    table = library_call(
        "usd",
        oid="table_000",
        keywords=[
            "central_supporting_table",
            "table",
            "white",
            "rectangular",
            "furniture",
            "center",
        ],
    )

    table_info = get_object_info(table)
    tabletop_z = table_info["max"][2]

    objects = library_call("tabletop_objects")
    objects = transform_shape(
        objects,
        translation_matrix((table_info["center"][0], table_info["center"][1], tabletop_z)),
    )

    return concat_shapes(table, objects)


@register()
def root_scene() -> Shape:
    return library_call("simple_table_with_bottle_and_bowl")