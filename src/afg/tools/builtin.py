import ast
import time

from afg.exceptions import ToolError
from afg.tools.decorator import tool


def evaluate_node(node):
    if isinstance(node, ast.Expression):
        return evaluate_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise ToolError("表达式里只能出现数字，不能出现布尔值")
        if isinstance(node.value, (int, float)):
            return node.value
        raise ToolError("表达式里只能出现数字", context={"value": repr(node.value)})

    if isinstance(node, ast.BinOp):
        left = evaluate_node(node.left)
        right = evaluate_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ToolError("除数不能为 0")
            return left / right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            # 限流：9**9**9 这种右结合写法会让解释器算到天荒地老，直接拒掉
            if right > 100:
                raise ToolError("指数太大，拒绝计算", context={"exponent": right})
            return left**right

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -evaluate_node(node.operand)
        if isinstance(node.op, ast.UAdd):
            return evaluate_node(node.operand)

    raise ToolError("表达式里有不支持的语法", context={"node": type(node).__name__})


@tool
def calculator(expr: str) -> str:
    """计算一个数学表达式的值。支持加减乘除、取余、乘方和括号，例如 37*89 或 (1+2)*3。
    只能算纯数字，表达式里不能出现变量名或函数调用。

    :param expr: 要计算的数学表达式，例如：37*89
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ToolError("表达式语法错误，没法解析", context={"expr": expr})
    return str(evaluate_node(tree))


FAKE_WEATHER = {
    "北京": {"condition": "晴", "temperature": 24, "humidity": 40},
    "上海": {"condition": "多云", "temperature": 27, "humidity": 65},
    "深圳": {"condition": "雷阵雨", "temperature": 31, "humidity": 80},
}


@tool
def get_weather(city: str) -> str:
    """查询一个城市的当前天气，返回天气状况、气温和湿度。
    目前只支持北京、上海、深圳三个城市，其他城市会返回错误。

    :param city: 中文城市名，可选值：北京、上海、深圳
    """
    if city not in FAKE_WEATHER:
        raise ToolError(
            "没有这个城市的天气数据",
            context={"city": city, "supported": list(FAKE_WEATHER.keys())},
        )
    row = FAKE_WEATHER[city]
    text = city + "：" + row["condition"]
    text += "，气温 " + str(row["temperature"]) + " 摄氏度"
    text += "，湿度 " + str(row["humidity"]) + "%"
    return text


@tool
def get_current_time() -> str:
    """获取本机当前的日期和时间（本地时区）。不需要任何参数，直接调用即可。"""
    return time.strftime("%Y-%m-%d %H:%M:%S")
