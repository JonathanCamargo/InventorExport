"""Topology graph visualization using NetworkX.

Builds a graph representation of the mechanism's kinematic topology
and renders it as an image.  Useful for debugging loop structures,
rigid groups, and parent-child relationships at a glance.
"""

import logging
from pathlib import Path

import networkx as nx

from inventor_exporter.model.assembly import AssemblyModel
from inventor_exporter.model.kinematic_tree import (
    KINEMATIC_JOINT_TYPES,
    LOOP_CLOSING_CONSTRAINT_TYPES,
    KinematicTree,
    _sanitize,
)

logger = logging.getLogger(__name__)


def build_topology_graph(
    model: AssemblyModel,
    ktree: KinematicTree,
    rigid_groups: dict[str, list[str]],
) -> nx.Graph:
    """Build a NetworkX graph of the mechanism topology.

    Nodes represent bodies (rigid groups are merged into single nodes).
    Edges represent joints and constraints, classified as tree edges,
    cut edges (closing loops), or ignored constraints.

    Args:
        model: The assembly model.
        ktree: Kinematic tree from ``classify_joints``.
        rigid_groups: Dict mapping representative to member body names.

    Returns:
        NetworkX Graph with node/edge attributes for visualization.
    """
    G = nx.Graph()

    # Map bodies to rigid group representative
    body_to_rep: dict[str, str] = {}
    for rep, members in rigid_groups.items():
        for m in members:
            body_to_rep[m] = rep

    def to_rep(name: str) -> str:
        return body_to_rep.get(name, name)

    # Collect tree joint constraint ids for classification
    tree_joint_ids = {id(c) for c in ktree.joint_for.values()}
    cut_joint_ids = {id(c) for c in ktree.cut_joints}

    # Add nodes — one per effective body (rigid group = single node)
    added_nodes: set[str] = set()
    for body in model.bodies:
        rep = to_rep(body.name)
        if rep in added_nodes:
            continue
        added_nodes.add(rep)

        members = rigid_groups.get(rep, [rep])
        is_root = rep in ktree.root_bodies or any(
            m in ktree.root_bodies for m in members
        )
        G.add_node(
            rep,
            label=_node_label(rep, members),
            is_ground=is_root and not any(
                rep in ktree.parent_of or m in ktree.parent_of
                for m in members
            ),
            is_group=len(members) > 1,
            members=members,
        )

    # Add edges from constraints
    for c in model.constraints:
        if c.is_rigid:
            continue
        a = to_rep(_sanitize(c.occurrence_one))
        b = to_rep(_sanitize(c.occurrence_two))
        if a == b:
            continue
        if a not in G or b not in G:
            continue

        # Classify edge
        if id(c) in tree_joint_ids:
            edge_class = "tree"
        elif id(c) in cut_joint_ids:
            edge_class = "cut"
        elif c.type in KINEMATIC_JOINT_TYPES or c.type in LOOP_CLOSING_CONSTRAINT_TYPES:
            edge_class = "ignored"
        else:
            continue

        # Avoid duplicate edges — networkx multigraph would complicate drawing
        key = f"{c.name}_{c.type}"
        G.add_edge(
            a, b,
            key=key,
            name=c.name or c.type,
            joint_type=c.type,
            edge_class=edge_class,
        )

    return G


def _node_label(rep: str, members: list[str]) -> str:
    """Build a human-readable node label."""
    if len(members) <= 1:
        return rep
    # Show group with member count
    return f"{rep}\n[{len(members)} parts]"


def _short_type(joint_type: str) -> str:
    """Shorten joint type for edge labels."""
    _map = {
        "rotational_joint": "revolute",
        "slider_joint": "prismatic",
        "cylindrical_joint": "cylindrical",
        "planar_joint": "planar",
        "ball_joint": "ball",
        "mate": "mate",
        "flush": "flush",
        "insert": "insert",
    }
    return _map.get(joint_type, joint_type)


def draw_topology(
    G: nx.Graph,
    output_path: Path,
    title: str = "Mechanism Topology",
) -> None:
    """Render the topology graph to an image file.

    Color scheme:
        - Nodes: gray = ground/root, light green = rigid group, light blue = body
        - Edges: blue solid = tree joint, red dashed = cut joint (loop closure),
                 orange dotted = ignored constraint

    Args:
        G: Topology graph from ``build_topology_graph``.
        output_path: Path for the output image (PNG recommended).
        title: Title shown on the figure.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    fig, ax = plt.subplots(1, 1, figsize=(10, 8))

    pos = nx.spring_layout(G, seed=42, k=2.0)

    # Node colors
    node_colors = []
    for n in G.nodes():
        data = G.nodes[n]
        if data.get("is_ground"):
            node_colors.append("#D3D3D3")
        elif data.get("is_group"):
            node_colors.append("#90EE90")
        else:
            node_colors.append("#87CEEB")

    # Classify edges
    tree_edges = [
        (u, v) for u, v, d in G.edges(data=True)
        if d.get("edge_class") == "tree"
    ]
    cut_edges = [
        (u, v) for u, v, d in G.edges(data=True)
        if d.get("edge_class") == "cut"
    ]
    ignored_edges = [
        (u, v) for u, v, d in G.edges(data=True)
        if d.get("edge_class") == "ignored"
    ]

    # Draw edges
    nx.draw_networkx_edges(
        G, pos, edgelist=tree_edges,
        edge_color="royalblue", width=2.5, ax=ax,
    )
    nx.draw_networkx_edges(
        G, pos, edgelist=cut_edges,
        edge_color="crimson", width=2.5, style="dashed", ax=ax,
    )
    nx.draw_networkx_edges(
        G, pos, edgelist=ignored_edges,
        edge_color="orange", width=1.5, style="dotted", ax=ax,
    )

    # Draw nodes
    labels = {n: G.nodes[n].get("label", n) for n in G.nodes()}
    nx.draw_networkx_nodes(
        G, pos, node_color=node_colors,
        node_size=2500, edgecolors="black", linewidths=1.0, ax=ax,
    )
    nx.draw_networkx_labels(G, pos, labels, font_size=7, ax=ax)

    # Edge labels
    edge_labels = {}
    for u, v, d in G.edges(data=True):
        name = d.get("name", "")
        jtype = _short_type(d.get("joint_type", ""))
        label = f"{name}\n({jtype})" if name else jtype
        edge_labels[(u, v)] = label
    nx.draw_networkx_edge_labels(
        G, pos, edge_labels, font_size=6, font_color="gray", ax=ax,
    )

    # Legend
    legend_elements = [
        Line2D([0], [0], color="royalblue", linewidth=2.5,
               label="Tree joint"),
        Line2D([0], [0], color="crimson", linewidth=2.5,
               linestyle="dashed", label="Cut joint (loop closure)"),
        Line2D([0], [0], color="orange", linewidth=1.5,
               linestyle="dotted", label="Ignored constraint"),
        Patch(facecolor="#D3D3D3", edgecolor="black", label="Ground / root"),
        Patch(facecolor="#90EE90", edgecolor="black", label="Rigid group"),
        Patch(facecolor="#87CEEB", edgecolor="black", label="Body"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=8)

    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.axis("off")
    plt.tight_layout()
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Wrote topology graph to %s", output_path)
