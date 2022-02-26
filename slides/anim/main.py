from manim import *

# My first manim animation, hope it's not too hard
# Please don't judge this code, it's not pretty I know, it wasn't meant to be in the project.
# It's just an animation to put in our slides.

is_dark = False

if not is_dark:
    config.background_color = WHITE
config.pixel_width = 400
config.pixel_height = 650

# Contrast color
CONTRAST = WHITE if is_dark else BLACK
BACKGROUND = BLACK if is_dark else WHITE


def create_textbox(color, string, opacity=0.5):
    box = Rectangle(   # create a box
        height=2, width=3, fill_color=color,
        fill_opacity=opacity, stroke_color=color
    )
    text = Text(string, color=CONTRAST).move_to(box.get_center())  # create text
    text.add_to_back(box)
    return text


class RecursiveEntityResolution(MovingCameraScene):
    def construct(self):
        self.camera.frame.scale(0.75).shift(DOWN*0.5)
        everything = VGroup()
        status = Text("IGDB game discovery", color=CONTRAST).shift(DOWN*8.5)

        def edit_status(to):
            new_status = Text(to, color=CONTRAST).move_to(status)
            return Transform(status, new_status)

        igdb = create_textbox(PURPLE, "IGDB")
        self.play(Create(igdb, run_time=0.5), Create(status))
        self.play(igdb.animate.shift(UP))

        igdb_games_titles = ['portal', 'half-life', 'gta']
        igdb_games = [create_textbox(CONTRAST, game, opacity=0) for game in igdb_games_titles]
        igdb_games[1].move_to(DOWN * 3)
        igdb_games[0].next_to(igdb_games[1], LEFT)
        igdb_games[2].next_to(igdb_games[1], RIGHT)
        everything.add(*igdb_games)
        lines = [Line(igdb.get_edge_center(DOWN), g.get_edge_center(UP), fill_color=CONTRAST, stroke_color=CONTRAST) for g in igdb_games]
        [line.set_z_index(-1) for line in lines]
        everything.add(*lines)
        self.play(
            *[FadeIn(g, run_time=1) for g in igdb_games],
            *[Create(line) for line in lines]
        )
        self.wait(0.4)
        self.play(edit_status("Entity Resolution"))
        self.wait(0.4)

        colors = [RED, GREEN, BLUE]
        self.play(
            *[g[0].animate.set_style(fill_color=c, stroke_color=c, fill_opacity=0.5) for g, c in zip(igdb_games, colors)],
            *[l.animate.set_style(stroke_color=c) for l, c in zip(lines, colors)]
        )
        self.wait(0.6)

        self.play(
            Transform(status, Text('Steam game discovery', color=CONTRAST).move_to(status).shift(DOWN*6)),
            self.camera.frame.animate.shift(DOWN*6),
        )

        # Steam entering the scene!
        steam = create_textbox(PURPLE, 'Steam')
        steam.shift(13*DOWN)
        everything.add(steam)
        self.play(Create(steam))
        steam_games_titles = ['half-life', 'portal 2', 'portal']
        steam_games = [create_textbox(CONTRAST, game, opacity=0) for game in steam_games_titles]
        steam_games[1].shift(DOWN * 9)
        steam_games[0].next_to(steam_games[1], LEFT)
        steam_games[2].next_to(steam_games[1], RIGHT)
        everything.add(*steam_games)
        steam_lines = [Line(steam.get_edge_center(UP), g.get_edge_center(DOWN), fill_color=CONTRAST, stroke_color=CONTRAST) for g in steam_games]
        [line.set_z_index(-1) for line in steam_lines]
        everything.add(*steam_lines)
        self.play(
            *[FadeIn(g, run_time=1) for g in steam_games],
            *[Create(line) for line in steam_lines]
        )

        self.wait(0.4)
        self.play(edit_status('Entity Discovery'))
        # Entity Resolution Phase
        arcs = []

        def arc_btw(a, b, txt):
            l = Line(a.get_edge_center(UP), b.get_edge_center(DOWN), fill_color=CONTRAST, stroke_color=CONTRAST)
            l.set_z_index(-5)
            arcs.append(l)
            everything.add(l)
            text = Text(txt, color=CONTRAST)
            text.set_z_index(5)
            text.add_background_rectangle(BACKGROUND, 0.8, buff=0.2)
            text.move_to(l.get_center())
            arcs.append(text)
            everything.add(text)

        arc_btw(steam_games[0], igdb_games[0], '0.3')
        arc_btw(steam_games[0], igdb_games[1], '0.9')
        SELECTION_COLOR = ORANGE
        self.play(AnimationGroup(steam_games[0].animate.set_color(SELECTION_COLOR), *[Create(arc) for arc in arcs], lag_ratio=0.1))

        self.play(AnimationGroup(steam_games[0].animate.set_color(CONTRAST), steam_games[1].animate.set_color(SELECTION_COLOR), lag_ratio=0.1))

        arc_btw(steam_games[2], igdb_games[0], '0.8')
        arc_btw(steam_games[2], igdb_games[2], '0.2')
        self.play(AnimationGroup(
            steam_games[1].animate.set_color(CONTRAST),
            steam_games[2].animate.set_color(SELECTION_COLOR),
            *[Create(arc) for arc in arcs[4:]],
            lag_ratio=0.1))
        self.play(AnimationGroup(steam_games[2].animate.set_color(CONTRAST)))
        self.wait()

        self.play(edit_status('Entity Resolution'))

        self.play(AnimationGroup(
            *[Uncreate(arcs[i]) for i in (0, 1, 6, 7)],
            arcs[2].animate.set_color(igdb_games[1][0].get_color()),
            arcs[4].animate.set_color(igdb_games[0][0].get_color()),
            lag_ratio=0.1
        ))
        self.wait()

        self.play(edit_status('Index writing'))

        colors = [GREEN, GOLD, RED]
        self.play(
            AnimationGroup(
                *[g[0].animate.set_style(fill_color=c, stroke_color=c, fill_opacity=0.5) for g, c in zip(steam_games, colors)],
                *[l.animate.set_style(stroke_color=c) for l, c in zip(steam_lines, colors)],
                lag_ratio=0.2
            )
        )
        # Assign entities to steam objects
        self.wait(0.5)
        self.play(edit_status('Done!'))

        self.wait(1.5)
        # Camera moving right = everything moves left
        self.play(self.camera.frame.animate.shift(RIGHT*15))

