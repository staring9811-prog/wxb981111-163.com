/* 发布配置。license 为 true 时，试玩到第 trialDays 天之后需要输入激活码才能继续。
 * 开发和 Claude Artifact 版本保持 false；对外售卖的发布包由 build.py --dist 生成，会把它改成 true。 */
window.JADE_CONFIG = { license: false, trialDays: 3, buyText: '激活码在卖家的闲鱼店铺购买，付款后自动发码。' };
