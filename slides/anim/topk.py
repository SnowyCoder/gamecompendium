from manim import *

is_dark = False

if not is_dark:
    config.background_color = WHITE
config.pixel_width = 500
config.pixel_height = 740

# Contrast color
CONTRAST = WHITE if is_dark else BLACK
BACKGROUND = BLACK if is_dark else WHITE


def create_textbox(color, string, score, opacity=0.5):
    group = VGroup()
    box = Rectangle(   # create a box
        height=2, width=3, fill_color=color,
        fill_opacity=opacity, stroke_color=color
    )
    text = Text(string, color=CONTRAST).move_to(box.get_center())  # create text
    scr_txt = Text(str(score), color=CONTRAST).move_to(box.get_center()).shift(UP * 0.6 + RIGHT)
    group.add(box, text, scr_txt)
    return group


class TopkMaxThreshold(MovingCameraScene):
    def create_stack(self, name, games):
        group = VGroup()
        txt = Text(name, color=CONTRAST)
        games = [create_textbox(PURPLE, name, score) for name, score in games]
        games[0].next_to(txt, DOWN)
        for i, g in enumerate(games[1:]):
            g.next_to(games[i], DOWN, buff=0)

        ddd = Text('...', color=CONTRAST)
        ddd.next_to(games[-1], DOWN)
        group.add(txt, *games, ddd)
        return group

    def create_threshold(self, index):
        box = Rectangle(   # create a box
            height=2, width=10, fill_color=BLUE,
            fill_opacity=0.5, stroke_color=BLUE
        )
        box.move_to(self.igdb[index + 1].get_center() * UP + LEFT * 0)
        threshold = max(int(self.igdb[index + 1][2].text), int(self.steam[index + 1][2].text))
        txt = Text(str(threshold), color=CONTRAST)
        txt.move_to(box.get_edge_center(RIGHT) + LEFT * 0.5)
        return VGroup(box, txt).set_z_index(-10)

    def edit_status(self, to):
        new_status = Text(to, color=CONTRAST).move_to(self.status)
        return Transform(self.status, new_status)

    def animated_topk_insert(self, elem):
        target_pos = next((i for i, x in enumerate(self.topk) if int(x[2].text) < int(elem[2].text)), len(self.topk))
        if target_pos == 0:
            elem.next_to(self.topkg[0], DOWN)
        else:
            elem.next_to(self.topk[target_pos - 1], DOWN, buff=0)

        animations = []
        self.topk.insert(target_pos, elem)
        self.topkg.add(elem)
        last = elem
        for e in self.topk[target_pos + 1:]:
            animations.append(e.animate.next_to(last, DOWN, buff=0))
            last = e

        return animations

    def topk_trim(self):
        if len(self.topk) <= 2:
            return
        anims = []
        for e in self.topk[2:]:
            anims.append(FadeOut(e))
            self.topkg.remove(e)
        self.topk = self.topk[:2]
        self.play(*anims)

    def run_cell(self, first, igdb_i, steam_i):
        self.play(self.edit_status("Compute row"))

        if first == 0:
            a_array, b_array = self.igdb, self.steam
            a_i, b_i = igdb_i, steam_i
            a_edge = RIGHT
        else:
            a_array, b_array = self.steam, self.igdb
            a_i, b_i = steam_i, igdb_i
            a_edge = LEFT

        self.play(a_array[a_i][0].animate.set_color(YELLOW))

        self.play(self.edit_status("Random Access Find"))
        if b_i >= 0:
            arc = Line(
                a_array[a_i][0].get_edge_center(a_edge),
                b_array[-1 if b_i < 0 else b_i][0].get_edge_center(-a_edge),
                color=CONTRAST
            )
            self.play(
                *([Create(arc)] +
                  ([b_array[b_i][0].animate.set_color(YELLOW)] if b_i >= 0 else [])),
            )
            found_c = 2
        else:
            arc = None
            found_c = 1
            self.wait(0.5)

        self.play(self.edit_status("Top-k insertion"))
        num = int(a_array[a_i][2].text) + (int(b_array[b_i][2].text) if b_i >= 0 else 0)
        avg = MathTex('\\frac{' + str(num) + '}{' + str(found_c) + '}', color=CONTRAST)
        if arc is not None:
            avg.move_to(arc.get_center()).shift(UP)
        else:
            avg.next_to(a_array[a_i], a_edge)
        self.play(Create(avg, run_time=0.5))
        self.play(Transform(avg, MathTex(str(num // found_c), color=CONTRAST).move_to(avg)))
        # Insert into top-k

        topk_0 = create_textbox(GREEN, a_array[a_i][1].text, num // found_c)
        anims = self.animated_topk_insert(topk_0)
        self.play(
            ReplacementTransform(a_array[a_i].copy(), topk_0),
            *anims
        )
        self.topk_trim()

        self.play(AnimationGroup(
            Uncreate(avg),
            *([Uncreate(arc)] if arc is not None else []),
            *[x.animate.set_color(CONTRAST) for x in ([a_array[a_i]] + ([b_array[b_i]] if b_i >= 0 else []))]
        ))

    def threshold_check(self, val):
        anims = []
        texs = []
        notok = []
        for el in self.topk:
            a = int(el[2].text)
            is_ok = a >= val
            tex = MathTex(str(a) + ' \\ge ' + str(val), color=(GREEN if is_ok else RED), font_size=60)
            tex.next_to(el, RIGHT)
            texs.append(tex)
            anims.append(Create(tex, run_time=0.3))
            if not is_ok:
                anims.append(el[0].animate.set_color(RED))
                notok.append(el)
        self.play(*anims)
        if len(notok) == 0:
            return
        self.wait(0.6)
        anims = [Uncreate(x, run_time=0.3) for x in texs]
        for el in notok:
            anims.append(el[0].animate.set_color(GREEN))
        self.play(*anims)

    def construct(self):
        self.camera.frame.scale(0.75)
        igdb = self.create_stack('IGDB', [('Portal', 10), ('Pokemon', 8), ('GTA', 4)])
        steam = self.create_stack('Steam', [('Stardew', 8), ('Portal', 4), ('GTA', 4)])
        self.igdb, self.steam = igdb, steam
        igdb.shift(UP*6.5 + LEFT * 3)
        steam.shift(UP*6.5 + RIGHT * 2)

        self.topk = []
        self.topkg = VGroup(
            Text("Top-2", color=CONTRAST)
        ).shift(DOWN * 1 + LEFT*0.5)

        threshold = self.create_threshold(0)
        self.play(
            AnimationGroup(*[FadeIn(x) for x in igdb], lag_ratio=0.1),
            AnimationGroup(*[FadeIn(x) for x in steam], lag_ratio=0.1),
            FadeIn(self.topkg[0]),
        )
        self.status = Text("Compute threshold", color=CONTRAST).shift(UP * 7.4)
        self.play(Create(self.status))
        self.play(*[Create(x) for x in threshold])

        self.run_cell(0, 1, 2)
        self.run_cell(1, -1, 1)

        self.play(self.edit_status('Update threshold'))
        self.play(Transform(threshold, self.create_threshold(1)))
        self.play(self.edit_status('Threshold check'))
        self.threshold_check(8)
        self.run_cell(0, 2, -1)

        self.play(self.edit_status('Update threshold'))
        self.play(Transform(threshold, self.create_threshold(2)))
        self.play(self.edit_status('Threshold check'))
        self.threshold_check(4)

        self.wait()
        self.play(self.edit_status('Done!'))
        self.wait(3)
        self.play(self.camera.frame.animate.shift(RIGHT*17))
