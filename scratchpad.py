from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
from argparse import ArgumentParser, Namespace
from time import sleep
from typing import Tuple
from Xlib.display import Display
from Xlib.xobject import icccm
from i3ipc import Connection, Rect, Event

logging.basicConfig(level=logging.DEBUG)
VERSION = "0.0.1"
SCRIPT_NAME = os.path.basename(__file__)
PID_DIR = os.environ.get("XDG_RUNTIME_DIR", "/tmp")

ANIMATION_FRAME_DELAY = 0.02
FRAME_COUNT = 20

xlib_display = Display()
xlib_root = xlib_display.screen(0)['root']

socket_path = str(subprocess.check_output("i3 --get-socketpath", shell=True).decode().strip())
i3 = Connection(socket_path=socket_path)
con = i3.get_tree()


def print_help():
    print(
        'Usage: %s [[-a <anchor>] [-d <size>] [-p <pos>] [-s <screen>]] [-m <edge>] [-t] [-u [-w][-o <opts>]] [-v] [-V] <command>\n' "$script_name")
    print('\nArguments:\n')
    print('\nExample:\n')
    print(' # Calendar at the bottom right of primary screen with 32px bottom margin:\n')
    print(' $ %s -d200x200 -abr -p0,-32 -wtu cal\n' "$script_name")


def create_arg_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="i3-scratchpad", description=
    """Executes a program in a positioned scratchpad, optionally wrapped in a URxvt window.\n
     Caches optional URxvt wrapper script and stores window id at XDG_RUNTIME_DIR based on command,\n
      so executing the same command will re-use the existing window, if it still exists.\n""")
    parser.version = VERSION
    # todo tl, tc support etc missing
    parser.add_argument("-a", "--anchor", metavar="anchor", type=str, help=
    """ Sets where to calculate position from. Valid values are\n
    top-left, top-center, top-right\n
    center-left, center-center, center-right\n
    bottom-left, bottom-center, bottom-right\n
    Can be shortened as: tl, tc, tr, cl, cc, cr, bl, bc, br\n
    Position will be calculated from anchor point of screen to anchor\n
    point of window. Default is center-center.\n """)

    parser.add_argument('-d', "--size", metavar="dimensions", type=str, help=
    """Dimensions of window in pixels, in WIDTHxHEIGHT format.\n 
    Percentages of the screen dimensions can be used as well. Default is 50%%x50%%\n""")

    #   parser.add_argument("help", metavar='h', help="Prints this help page.")
    parser.add_argument("-m", "--move", metavar="edge", help=
    """ Animates the movement to target position from specified edge.\n
    Valid values are top, left, bottom, right, or short t, l, b, r\n """)
    parser.add_argument("-o", "--opts", metavar="opts", help="Extra URxvt options to pass.")
    parser.add_argument("-p", "--pos", metavar='pos', help=
    """Position of terminal on pixels, in X,Y format.\n
    Negative values can be used as well. Default is 0,0\n """)
    parser.add_argument("-s", "--screen", metavar='screen',
                        help="Screen identifier, as listed in xrandr. Falls back to primary screen.\n")
    parser.add_argument("-t", "--toggle", action="store_true", help="Toggles the window")
    parser.add_argument("-u", "--urxvt", action="store_true",
                        help="Use URxvt terminal to launch the command - for command line apps.\n")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose")
    #    parser.add_argument("version", action='version', help="Print version information")
    parser.add_argument("-w", "--wait", action="store_true", help=
    """ Hides the cursor and waits for keypress before closing the\n
    terminal window. Useful for commands immediately returning.\n""")
    parser.add_argument("command")
    return parser


def main():
    parser = create_arg_parser()
    args = parser.parse_args()
    validate_input(args)
    screen = Screen.get_active_screen()
    window = Window.from_args(args, screen)
    cmd_hash = int(hashlib.md5(args.command.encode()).hexdigest(), 16)
    wid_file = f"{PID_DIR}/i3-sp-{cmd_hash}"
    if already_running(args, window, screen, wid_file):
        sys.exit(0)
    start_and_save_wid_and_pid(args, window, screen, wid_file)


def get_xlib_window(window_id: int):
    return xlib_display.create_resource_object("window", window_id)


def get_window_state(window_id: int) -> str:
    x_window = get_xlib_window(window_id)
    atom = x_window.display.get_atom('WM_STATE')
    y= x_window.get_property(atom, atom, 0, icccm.WMState.static_size // 4)
    logging.info(y)
    logging.warning("HELLO")
    return x_window.get_wm_state()


def already_running(args: Namespace, window: Window, screen: Screen, wid_file: str) -> bool:
    logging.info(f"Checking wid file {wid_file}")
    window_id: int = None
    cid: int = None
    if os.path.exists(wid_file):
        with open(wid_file, "r") as f:
            entries = f.read().split()
            window_id, cid = int(entries[0]), int(entries[1])

    window.window_id = window_id
    if window_id:
        logging.info(f"Last window id was {window_id}")
        i3_window = con.find_by_window(window_id)
        if i3_window:
            logging.info("Window still exists")
            if cid:
                window_cid = i3_window.id
                logging.info(f"Cid of window is {window_cid}")
                if cid != window_cid:
                    logging.error(f"PID does not match, window id reused?")
                    return False
            else:
                logging.warning("Last pid not found")
            if args.toggle:
                window_state = get_window_state(window_id)
                logging.info(f"Toggle mode on, current window state is {window_state}")
                if window_state['state'] != 0:  # https://tronche.com/gui/x/icccm/sec-4.html#s-4.1.3.1
                    logging.info("Moving to scratchpad")
                    window.hide(args, screen)
                    return True

            window.show_window_in_position(args, screen)
            return True
    return False


window_update = None


def process_event(connection, window):
    global window_update
    connection.command('floating enable')
    window_update = window
    i3.main_quit()


def start_and_save_wid_and_pid(args: Namespace, window: Window, screen: Screen, wid_file: str) -> int:
    global window_update
    if args.urxvt:
        create_urxvt_wrapper()

    command = args.command
    logging.info(f"Launching command {command}")
    i3_command = f"exec --no-startup-id \"{command}\""

    tree = i3.get_tree()
    tree.command(i3_command)
    i3.on(Event.WINDOW_NEW, process_event)
    i3.main()

    window_id = window_update.ipc_data['container']['window']
    window.window_id = window_id
    if not window_id:
        logging.warning(f"Cannot find window with id {window_id}")
        os.remove(wid_file)
        return 1

    pid = window_update.ipc_data['container']['id']
    if not pid:
        logging.warning(f"Cannot find pid for window id {window_id}")
        os.remove(wid_file)
        return 1

    logging.info(f"PID of window is {pid}")
    logging.debug(f'Saving window_id {window_id} and pid {pid} to wid file {wid_file}')
    with open(wid_file, "w") as f:
        f.write(f"{window_id} {pid}")

    window.show_window_in_position(args, screen)


def parse_anchor(args: Namespace) -> Tuple[str, str]:
    anchor = args.anchor
    y_axis, x_axis = anchor.split("-", maxsplit=1)
    return x_axis, y_axis


def validate_input(args: Namespace):
    x_axis, y_axis = parse_anchor(args)
    if y_axis not in ["top", "center", "bottom"] or x_axis not in ["left", "center", "right"]:
        logging.warning(f"Anchor {args.anchor} is invalid. See {SCRIPT_NAME} -h")

    move = args.move
    if move not in ["top", "bottom", "left", "right"]:
        logging.warning(f"Move {move} is invalid. See {SCRIPT_NAME} -h")


def parse_percentage(number_str: str) -> int:
    return int(number_str.rstrip("%"))


def create_urxvt_wrapper():
    pass


class Screen(Rect):
    @staticmethod
    def get_active_screen() -> Screen:
        workspaces = i3.get_workspaces()
        focused_workspace = [w for w in workspaces if w.focused][0]
        output = [output for output in i3.get_outputs() if output.name == focused_workspace.output][0]
        return Screen(output.rect.__dict__)


class Window(Rect):
    window_id: int
    x_offset: int
    y_offset: int

    def __init__(self, x: int, y: int, width: int, height: int, x_offset: int, y_offset: int):
        super().__init__({"x": x, "y": y, "height": height, "width": width})
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.window_id = None
        logging.debug(f'Calculated window dimensions are [ x: {self.x} y: {self.y} w: {self.width} h: {self.height}')

    @staticmethod
    def from_args(args: Namespace, screen: Screen) -> Window:
        width, height = Window.parse_dimensions(args, screen)
        x_pos, y_pos = Window.parse_position(args, screen, width, height)
        return Window(x=x_pos, y=y_pos, width=width, height=height, x_offset=screen.x, y_offset=screen.y)

    @staticmethod
    def parse_dimensions(args: Namespace, screen: Screen) -> Tuple[int, int]:
        dimensions: str = args.size
        if dimensions:
            width, height = dimensions.split("x", maxsplit=1)
        else:
            width, height = "-50%", "-50%"
        if '%' in width:
            width = screen.width * parse_percentage(width) / 100
        if '%' in height:
            height = screen.height * parse_percentage(height) / 100
        return width, height

    @staticmethod
    def parse_position(args: Namespace, screen: Screen, width: int, height: int) -> Tuple[int, int]:
        pos: str = args.pos
        if pos:
            x, y = pos.split(",", maxsplit=1)
        else:
            x, y = -0, -0
        x_axis, y_axis = parse_anchor(args)
        if x_axis == "left":
            x += screen.x
        elif x_axis == "center":
            x += ((screen.width - width) / 2) + screen.x
        elif x_axis == "right":
            x += screen.width - width + screen.x

        if y_axis == "top":
            y += screen.y
        elif y_axis == "center":
            y += ((screen.height - height) / 2) + screen.y
        elif y_axis == "bottom":
            y += screen.height - height + screen.y
        return x, y

    def show_window_in_position(self, args: Namespace, screen: Screen):
        if not args.move:
            logging.debug('Moving to scratchpad, showing and resizing')
            i3.command(
                f'[id=\"{self.window_id}\"] move to scratchpad;[id=\"{self.window_id}\"] scratchpad show;[id=\"{self.window_id}\"] move position {int(self.x_pos)} px {int(self.y_pos)} px;[id=\"{self.window_id}\"] resize set {int(self.width)} px {int(self.height)} px')
            return 0

        x_start, y_start = self.x, self.y
        x_inc, y_inc = 0, 0
        x_end, y_end = self.x, self.y

        if args.move == "top":
            y_start = self.y_offset - self.height + 1
            y_inc = (self.y - y_start) / FRAME_COUNT
            self.y = y_start
        elif args.move == "bottom":
            y_start = self.y_offset + screen.height - 1
            y_inc = (self.y - y_start) / FRAME_COUNT
            self.y = y_start
        elif args.move == "left":
            x_start = self.x_offset - self.width + 1
            x_inc = (self.x - x_start) / FRAME_COUNT
            self.x = x_start
        elif args.move == "right":
            x_start = self.x_offset + screen.width - 1
            x_inc = (self.x - x_start) / FRAME_COUNT
            self.x = x_start
        i3.command(
            f'[id=\"{self.window_id}\"] move to scratchpad;[id=\"{self.window_id}\"] scratchpad show;[id=\"{self.window_id}\"] move absolute position {int(self.x)} px {int(self.y)} px;[id=\"{self.window_id}\"] resize set {int(self.width)} px {int(self.height)} px')
        logging.debug("Starting show animation")
        self.animate(x_start, x_inc, x_end, y_start, y_inc, y_end)
        logging.info("Animation completed")
        i3.command(f'[id=\"{self.window_id}\"] move absolute position {int(x_end)} px {int(y_end)} px')

    def hide(self, args: Namespace, screen: Screen):
        if args.move:

            x_start, y_start = self.x, self.y
            x_inc, y_inc = 0, 0
            x_end, y_end = self.x, self.y

            if args.move == "top":
                y_end = self.y_offset - self.height
                y_inc = (y_end - self.y) / FRAME_COUNT
            elif args.move == "bottom":
                y_end = self.y_offset + screen.height - 1
                y_inc = (y_end - self.y) / FRAME_COUNT
            elif args.move == "left":
                x_end = self.x_offset - self.width
                x_inc = (x_end - self.x) / FRAME_COUNT
            elif args.move == "right":
                x_end = self.x_offset + screen.width - 1
                x_inc = (x_end - self.x) / FRAME_COUNT
            logging.info("Starting hide animation")
            self.animate(x_start, x_inc, x_end, y_start, y_inc, y_end)
            logging.info("Animation completed")
        i3.command(f'[id=\"{self.window_id}\"] move to scratchpad;')

    def animate(self, x_start: int, x_inc: int, x_end: int, y_start: int, y_inc: int, y_end: int) -> None:
        while x_inc < 0 and self.x > x_end or x_inc > 0 and self.x < x_end or y_inc < 0 and self.y > y_end or y_inc > 0 and self.y < y_end:
            logging.debug(f"Moving to [ {self.x} {self.y} ] with increment [ {x_inc} {y_inc} ]")
            i3.command(f'[id=\"{self.window_id}\"] move absolute position {int(self.x)} px {int(self.y)} px')

            self.x += x_inc
            self.y += y_inc

            if self.x < x_start and x_inc <= 0 or self.x > x_start and x_inc >= 0:
                x_inc = x_inc * 125 / 100
            else:
                x_inc = x_inc * 100 / 125
            if self.y < y_start and y_inc <= 0 or self.y > y_start and y_inc >= 0:
                y_inc = y_inc * 125 / 100
            else:
                y_inc = y_inc * 100 / 125

            sleep(ANIMATION_FRAME_DELAY)


if __name__ == '__main__':
    main()
