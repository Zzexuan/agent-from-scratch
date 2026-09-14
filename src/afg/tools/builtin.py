import ast
import time

from afg.exceptions import ToolError
from afg.tools.base import BaseTool


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


class CalculatorTool(BaseTool):
    name = "calculator"
    description = (
        "计算一个数学表达式的值。参数 expr 是表达式字符串，"
        "支持加减乘除、取余、乘方和括号，例如 37*89 或 (1+2)*3。"
        "只能算纯数字，表达式里不能出现变量名或函数调用。"
    )

    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "expr": {
                    "type": "string",
                    "description": "要计算的数学表达式，例如：37*89",
                },
            },
            "required": ["expr"],
        }

    def run(self, **kwargs):
        expr = kwargs["expr"]
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError:
            raise ToolError("表达式语法错误，没法解析", context={"expr": expr})
        value = evaluate_node(tree)
        return str(value)


FAKE_WEATHER = {
    "北京": {"condition": "晴", "temperature": 24, "humidity": 40},
    "上海": {"condition": "多云", "temperature": 27, "humidity": 65},
    "深圳": {"condition": "雷阵雨", "temperature": 31, "humidity": 80},
}


class WeatherTool(BaseTool):
    name = "get_weather"
    description = (
        "查询一个城市的当前天气。参数 city 是中文城市名，"
        "目前只支持北京、上海、深圳三个城市，其他城市会返回错误。"
        "返回该城市的天气状况、气温和湿度。"
    )

    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "中文城市名，可选值：北京、上海、深圳",
                },
            },
            "required": ["city"],
        }

    def run(self, **kwargs):
        city = kwargs["city"]
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


class CurrentTimeTool(BaseTool):
    name = "get_current_time"
    description = "获取本机当前的日期和时间（本地时区）。这个工具不需要任何参数，直接调用即可。"

    def parameters(self):
        return {"type": "object", "properties": {}}

    def run(self, **kwargs):
        return time.strftime("%Y-%m-%d %H:%M:%S")
