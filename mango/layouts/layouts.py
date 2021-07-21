# # ⚠ Warning
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
# LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
# NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# [🥭 Mango Markets](https://mango.markets/) support is available at:
#   [Docs](https://docs.mango.markets/)
#   [Discord](https://discord.gg/67jySBhxrg)
#   [Twitter](https://twitter.com/mangomarkets)
#   [Github](https://github.com/blockworks-foundation)
#   [Email](mailto:hello@blockworks.foundation)

# # 🥭 Layouts
#
# This file contains structure layouts to load the sometimes-opaque data blobs from Solana
# accounts.
#
# The idea is to have one data-encapsulating class (in [BaseModel](BaseModel.ipynb)) for
# each type, as well as one or more LAYOUT structures. So for example `Group` loads `GROUP`
# but in future will also be able to load `GROUP_V2`.
#
# The general approach is:
# * Define one (or more) layouts to read in the data blob
# * Use the data from the data blob to construct a more useful strongly-typed object
#
# So for example `GROUP` is defined below but it's a low-level dependency. In general, code
# should depend and work with the `Group` class, not the `GROUP` structure.
#
# Note: usize is a u64 on Solana, so a regular DecimalAdapter() works


import construct
import datetime
import typing

from decimal import Decimal
from solana.publickey import PublicKey


# # Adapters
#
# These are adapters for the construct package to simplify our struct declarations.

# ## DecimalAdapter class
#
# A simple construct `Adapter` that lets us use `Decimal`s directly in our structs.


class DecimalAdapter(construct.Adapter):
    def __init__(self, size: int = 8):
        construct.Adapter.__init__(self, construct.BytesInteger(size, swapped=True))

    def _decode(self, obj, context, path) -> Decimal:
        return Decimal(obj)

    def _encode(self, obj, context, path) -> int:
        # Can only encode int values.
        return int(obj)


# ## FloatAdapter class
#
# Some numbers are packaged as 16-bytes to represent a `float`. The way to get the `float`
# is to take the 16-byte int value and divide it by 2 to the power 64. In Javascript this
# would be:
# ```
# return intValue / Math.pow(2, 64);
# ```
# From [Daffy on Discord](https://discordapp.com/channels/791995070613159966/820390560085835786/841327936383614987):
# > It's a u128 underneath. Interpreted as a binary fixed point number where teh fixed point is right at the middle
#
# > Just interpret as u128 then divide by 2 ^ 64. Also make sure there are enough units of precision available
#
# > If you look at our mango-client-ts we just use the javascript number which is a float64 and that has caused some issues for us because of rounding issues.
#
# This is a simple construct `Adapter` that lets us use these float values directly in our
# structs. We do as Daffy says, but we can handle arbitrary sizes, not just u128. (The
# constructor takes a size - in bytes, like the rest of our code - and calculates the
# divisor so the mid-point of the whole sequence of bits is the fixed point.)


class FloatAdapter(construct.Adapter):
    def __init__(self, size: int = 16):
        self.size = size
        construct.Adapter.__init__(self, construct.BytesInteger(size, swapped=True))

        # Our size is in bytes but we want to work with bits here.
        bit_size = self.size * 8

        # For our string of bits, our 'fixed point' is right in the middle.
        fixed_point = bit_size / 2

        # So our divisor is 2 to the power of the fixed point
        self.divisor = Decimal(2 ** fixed_point)

    def _decode(self, obj, context, path) -> Decimal:
        return Decimal(obj) / self.divisor

    def _encode(self, obj, context, path) -> bytes:
        return bytes(obj)


# ## SignedDecimalAdapter class
#
# Another simple `Decimal` `Adapter` but this one specifically works with signed decimals.

class SignedDecimalAdapter(construct.Adapter):
    def __init__(self, size: int = 8):
        construct.Adapter.__init__(self, construct.BytesInteger(size, signed=True, swapped=True))

    def _decode(self, obj, context, path) -> Decimal:
        return Decimal(obj)

    def _encode(self, obj, context, path) -> int:
        # Can only encode int values.
        return int(obj)


# ## PublicKeyAdapter
#
# A simple construct `Adapter` that lets us use `PublicKey`s directly in our structs.


class PublicKeyAdapter(construct.Adapter):
    def __init__(self):
        construct.Adapter.__init__(self, construct.Bytes(32))

    def _decode(self, obj, context, path) -> typing.Optional[PublicKey]:
        if (obj is None) or (obj == bytes([0] * 32)):
            return None
        return PublicKey(obj)

    def _encode(self, obj, context, path) -> bytes:
        return bytes(obj)


# ## DatetimeAdapter
#
# A simple construct `Adapter` that lets us load `datetime`s directly in our structs.


class DatetimeAdapter(construct.Adapter):
    def __init__(self):
        construct.Adapter.__init__(self, construct.BytesInteger(8, swapped=True))

    def _decode(self, obj, context, path) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(obj)

    def _encode(self, obj, context, path) -> bytes:
        return bytes(obj)


# ## FloatI80F48Adapter
#
# Rust docs say a fixed::types::I80F48 is:
# "FixedI128 with 80 integer bits and 48 fractional bits.""
#
# So it's 128 bits, or 16 bytes, long, and the first 10 bytes are the
# integer part and the last 6 bytes are the fractional part.


class FloatI80F48Adapter(construct.Adapter):
    def __init__(self):
        self.size = 16
        construct.Adapter.__init__(self, construct.BytesInteger(self.size, swapped=True))

        # For our string of bits, our 'fixed point' is between the 10th byte and 11th byte. We want
        # the last 6 bytes to be fractional, so:
        fixed_point_in_bits = 8 * 6

        # So our divisor is 2 to the power of the fixed point
        self.divisor = Decimal(2 ** fixed_point_in_bits)

    def _decode(self, obj, context, path) -> Decimal:
        # How many decimal places precision should we allow for an I80F48? We could:
        # return round(Decimal(obj) / self.divisor, 12)
        return Decimal(obj) / self.divisor

    def _encode(self, obj, context, path) -> bytes:
        return bytes(obj)


# ## BookPriceAdapter
#
# This is a workaround for the way Serum encodes order IDs.
#
# The order ID is 16 bytes, which is fine. But:
# * The first 8 bytes are also the sequence_number.
# * The last 8 bytes are also the price.
#
# Really, it'd be nice if this adapter could place 3 keys in the layout struct, but I haven't
# found out how to do that. So as a quick workaround, we return the three keys in their own
# dictionary.

class BookPriceAdapter(construct.Adapter):
    def __init__(self):
        construct.Adapter.__init__(self, construct.Bytes(16))

    def _decode(self, obj, context, path) -> typing.Dict[str, Decimal]:
        order_id = Decimal(int.from_bytes(obj, 'little', signed=False))
        low_order = obj[:8]
        high_order = obj[8:]
        sequence_number = Decimal(int.from_bytes(low_order, 'little', signed=False))
        price = Decimal(int.from_bytes(high_order, 'little', signed=False))

        return {
            "order_id": order_id,
            "price": price,
            "sequence_number": sequence_number
        }

    def _encode(self, obj, context, path) -> int:
        # Not done yet
        raise NotImplementedError()


# ## OrderBookNodeAdapter
#
# An OrderBook node can be one of 5 different types, all the same size but differentiated by their tag.
#
# I thought there might be a way to get this working using the `construct.Select()` mechanism, but it
# didn't work - complaining about the use of sizeof(), even though all NODE layouts are exactly 72 bytes.
_NODE_SIZE = 88


class OrderBookNodeAdapter(construct.Adapter):
    def __init__(self):
        construct.Adapter.__init__(self, construct.Bytes(_NODE_SIZE))

    def _decode(self, obj, context, path) -> Decimal:
        any_node = ANY_NODE.parse(obj)
        if any_node.tag == Decimal(0):
            return UNINITIALIZED_BOOK_NODE.parse(obj)
        elif any_node.tag == Decimal(1):
            return INNER_BOOK_NODE.parse(obj)
        elif any_node.tag == Decimal(2):
            return LEAF_BOOK_NODE.parse(obj)
        elif any_node.tag == Decimal(3):
            return FREE_BOOK_NODE.parse(obj)
        elif any_node.tag == Decimal(4):
            return LAST_FREE_BOOK_NODE.parse(obj)

        raise Exception(f"Unknown node type tag: {any_node.tag}")

    def _encode(self, obj, context, path) -> int:
        # Not done yet
        raise NotImplementedError()


# # Layout Structs

# ## ACCOUNT_FLAGS
#
# Here's the [Serum Rust structure](https://github.com/project-serum/serum-dex/blob/master/dex/src/state.rs):
# ```
# #[derive(Copy, Clone, BitFlags, Debug, Eq, PartialEq)]
# #[repr(u64)]
# pub enum AccountFlag {
#     Initialized = 1u64 << 0,
#     Market = 1u64 << 1,
#     OpenOrders = 1u64 << 2,
#     RequestQueue = 1u64 << 3,
#     EventQueue = 1u64 << 4,
#     Bids = 1u64 << 5,
#     Asks = 1u64 << 6,
#     Disabled = 1u64 << 7,
# }
# ```
ACCOUNT_FLAGS = construct.BitsSwapped(
    construct.BitStruct(
        "initialized" / construct.Flag,
        "market" / construct.Flag,
        "open_orders" / construct.Flag,
        "request_queue" / construct.Flag,
        "event_queue" / construct.Flag,
        "bids" / construct.Flag,
        "asks" / construct.Flag,
        "disabled" / construct.Flag,
        construct.Padding(7 * 8)
    )
)


# ## TOKEN_ACCOUNT


TOKEN_ACCOUNT = construct.Struct(
    "mint" / PublicKeyAdapter(),
    "owner" / PublicKeyAdapter(),
    "amount" / DecimalAdapter(),
    "padding" / construct.Padding(93)
)


# ## OPEN_ORDERS
#
# Trying to use the `OPEN_ORDERS_LAYOUT` and `OpenOrdersAccount` from `pyserum` just
# proved too probelmatic. (`OpenOrdersAccount` doesn't expose `referrer_rebate_accrued`,
# for instance.)


OPEN_ORDERS = construct.Struct(
    construct.Padding(5),
    "account_flags" / ACCOUNT_FLAGS,
    "market" / PublicKeyAdapter(),
    "owner" / PublicKeyAdapter(),
    "base_token_free" / DecimalAdapter(),
    "base_token_total" / DecimalAdapter(),
    "quote_token_free" / DecimalAdapter(),
    "quote_token_total" / DecimalAdapter(),
    "free_slot_bits" / DecimalAdapter(16),
    "is_bid_bits" / DecimalAdapter(16),
    "orders" / construct.Array(128, DecimalAdapter(16)),
    "client_ids" / construct.Array(128, DecimalAdapter()),
    "referrer_rebate_accrued" / DecimalAdapter(),
    "padding" / construct.Padding(7)
)


MAX_TOKENS: int = 32
MAX_PAIRS: int = MAX_TOKENS - 1
MAX_NODE_BANKS: int = 8
QUOTE_INDEX: int = MAX_TOKENS - 1
MAX_BOOK_NODES: int = 1024

DATA_TYPE = construct.Enum(construct.Int8ul, Group=0, Account=1, RootBank=2,
                           NodeBank=3, PerpMarket=4, Bids=5, Asks=6, Cache=7, EventQueue=8)


# # 🥭 METADATA
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/state.rs):
# ```
# #[derive(Copy, Clone, Pod, Default)]
# #[repr(C)]
# /// Stores meta information about the `Account` on chain
# pub struct MetaData {
#     pub data_type: u8,
#     pub version: u8,
#     pub is_initialized: bool,
#     pub padding: [u8; 5], // This makes explicit the 8 byte alignment padding
# }
# ```
METADATA = construct.Struct(
    "data_type" / DATA_TYPE,
    "version" / DecimalAdapter(1),
    "is_initialized" / DecimalAdapter(1),
    "padding" / construct.Padding(5)
)


# # 🥭 TOKEN_INFO
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/state.rs):
# ```
# #[derive(Copy, Clone, Pod)]
# #[repr(C)]
# pub struct TokenInfo {
#     pub mint: Pubkey,
#     pub root_bank: Pubkey,
#     pub decimals: u8,
#     pub padding: [u8; 7],
# }
# ```
TOKEN_INFO = construct.Struct(
    "mint" / PublicKeyAdapter(),
    "root_bank" / PublicKeyAdapter(),
    "decimals" / DecimalAdapter(1),
    "padding" / construct.Padding(7)
)


# # 🥭 SPOT_MARKET_INFO
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/state.rs):
# ```
# #[derive(Copy, Clone, Pod)]
# #[repr(C)]
# pub struct SpotMarketInfo {
#     pub spot_market: Pubkey,
#     pub maint_asset_weight: I80F48,
#     pub init_asset_weight: I80F48,
#     pub maint_liab_weight: I80F48,
#     pub init_liab_weight: I80F48,
#     pub liquidation_fee: I80F48,
# }
# ```
SPOT_MARKET_INFO = construct.Struct(
    "spot_market" / PublicKeyAdapter(),
    "maint_asset_weight" / FloatI80F48Adapter(),
    "init_asset_weight" / FloatI80F48Adapter(),
    "maint_liab_weight" / FloatI80F48Adapter(),
    "init_liab_weight" / FloatI80F48Adapter(),
    "liquidation_fee" / FloatI80F48Adapter()
)

# # 🥭 PERP_MARKET_INFO
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/state.rs):
# ```
# #[derive(Copy, Clone, Pod)]
# #[repr(C)]
# pub struct PerpMarketInfo {
#     pub perp_market: Pubkey, // One of these may be empty
#     pub maint_asset_weight: I80F48,
#     pub init_asset_weight: I80F48,
#     pub maint_liab_weight: I80F48,
#     pub init_liab_weight: I80F48,
#     pub liquidation_fee: I80F48,
#     pub maker_fee: I80F48,
#     pub taker_fee: I80F48,
#     pub base_lot_size: i64,  // The lot size of the underlying
#     pub quote_lot_size: i64, // min tick
# }
# ```
PERP_MARKET_INFO = construct.Struct(
    "perp_market" / PublicKeyAdapter(),
    "maint_asset_weight" / FloatI80F48Adapter(),
    "init_asset_weight" / FloatI80F48Adapter(),
    "maint_liab_weight" / FloatI80F48Adapter(),
    "init_liab_weight" / FloatI80F48Adapter(),
    "liquidation_fee" / FloatI80F48Adapter(),
    "maker_fee" / FloatI80F48Adapter(),
    "taker_fee" / FloatI80F48Adapter(),
    "base_lot_size" / SignedDecimalAdapter(),
    "quote_lot_size" / SignedDecimalAdapter(),
)

# # 🥭 GROUP
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/state.rs):
# ```
# #[derive(Copy, Clone, Pod, Loadable)]
# #[repr(C)]
# pub struct MangoGroup {
#     pub meta_data: MetaData,
#     pub num_oracles: usize, // incremented every time add_oracle is called
#
#     pub tokens: [TokenInfo; MAX_TOKENS],
#     pub spot_markets: [SpotMarketInfo; MAX_PAIRS],
#     pub perp_markets: [PerpMarketInfo; MAX_PAIRS],
#
#     pub oracles: [Pubkey; MAX_PAIRS],
#
#     pub signer_nonce: u64,
#     pub signer_key: Pubkey,
#     pub admin: Pubkey,          // Used to add new markets and adjust risk params
#     pub dex_program_id: Pubkey, // Consider allowing more
#     pub mango_cache: Pubkey,
#     pub valid_interval: u64,
#
#     // DAO vault is funded by the Mango DAO with USDC and can be withdrawn by the DAO
#     pub dao_vault: Pubkey,
#     pub srm_vault: Pubkey,
#     pub msrm_vault: Pubkey,
# }
# ```
GROUP = construct.Struct(
    "meta_data" / METADATA,
    "num_oracles" / DecimalAdapter(),
    "tokens" / construct.Array(MAX_TOKENS, TOKEN_INFO),
    "spot_markets" / construct.Array(MAX_PAIRS, SPOT_MARKET_INFO),
    "perp_markets" / construct.Array(MAX_PAIRS, PERP_MARKET_INFO),
    "oracles" / construct.Array(MAX_PAIRS, PublicKeyAdapter()),
    "signer_nonce" / DecimalAdapter(),
    "signer_key" / PublicKeyAdapter(),
    "admin" / PublicKeyAdapter(),
    "dex_program_id" / PublicKeyAdapter(),
    "cache" / PublicKeyAdapter(),
    "valid_interval" / DecimalAdapter(),
    "dao_vault" / PublicKeyAdapter(),
    "srm_vault" / PublicKeyAdapter(),
    "msrm_vault" / PublicKeyAdapter()
)

# # 🥭 ROOT_BANK
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/state.rs):
# ```
# /// This is the root bank for one token's lending and borrowing info
# #[derive(Copy, Clone, Pod, Loadable)]
# #[repr(C)]
# pub struct RootBank {
#     pub meta_data: MetaData,
#
#     pub optimal_util: I80F48,
#     pub optimal_rate: I80F48,
#     pub max_rate: I80F48,
#
#     pub num_node_banks: usize,
#     pub node_banks: [Pubkey; MAX_NODE_BANKS],
#
#     pub deposit_index: I80F48,
#     pub borrow_index: I80F48,
#     pub last_updated: u64,
#
#     padding: [u8; 64], // used for future expansions
# }
# ```
ROOT_BANK = construct.Struct(
    "meta_data" / METADATA,
    "optimal_util" / FloatI80F48Adapter(),
    "optimal_rate" / FloatI80F48Adapter(),
    "max_rate" / FloatI80F48Adapter(),

    "num_node_banks" / DecimalAdapter(),
    "node_banks" / construct.Array(MAX_NODE_BANKS, PublicKeyAdapter()),
    "deposit_index" / FloatI80F48Adapter(),
    "borrow_index" / FloatI80F48Adapter(),
    "last_updated" / DatetimeAdapter(),

    construct.Padding(64)
)

# # 🥭 NODE_BANK
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/state.rs):
# ```
# #[derive(Copy, Clone, Pod, Loadable)]
# #[repr(C)]
# pub struct NodeBank {
#     pub meta_data: MetaData,
#
#     pub deposits: I80F48,
#     pub borrows: I80F48,
#     pub vault: Pubkey,
# }
# ```
NODE_BANK = construct.Struct(
    "meta_data" / METADATA,
    "deposits" / FloatI80F48Adapter(),
    "borrows" / FloatI80F48Adapter(),
    "vault" / PublicKeyAdapter()
)

# # 🥭 PERP_OPEN_ORDERS
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/state.rs):
# ```
# #[derive(Copy, Clone, Pod)]
# #[repr(C)]
# pub struct PerpOpenOrders {
#     pub bids_quantity: i64, // total contracts in sell orders
#     pub asks_quantity: i64, // total quote currency in buy orders
#     pub is_free_bits: u32,
#     pub is_bid_bits: u32,
#     pub orders: [i128; 32],
#     pub client_order_ids: [u64; 32],
# }
# ```
PERP_OPEN_ORDERS = construct.Struct(
    "bids_quantity" / SignedDecimalAdapter(),
    "asks_quantity" / SignedDecimalAdapter(),
    "free_slot_bits" / DecimalAdapter(4),
    "is_bid_bits" / DecimalAdapter(4),
    "orders" / construct.Array(MAX_TOKENS, SignedDecimalAdapter(16)),
    "client_order_ids" / construct.Array(MAX_TOKENS, SignedDecimalAdapter())
)

# # 🥭 PERP_ACCOUNT
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/state.rs):
# ```
# #[derive(Copy, Clone, Pod)]
# #[repr(C)]
# pub struct PerpAccount {
#     pub base_position: i64,     // measured in base lots
#     pub quote_position: I80F48, // measured in native quote
#
#     pub long_settled_funding: I80F48,
#     pub short_settled_funding: I80F48,
#     pub open_orders: PerpOpenOrders,
#     pub liquidity_points: I80F48,
# }
# ```
PERP_ACCOUNT = construct.Struct(
    "base_position" / SignedDecimalAdapter(),
    "quote_position" / FloatI80F48Adapter(),
    "long_settled_funding" / FloatI80F48Adapter(),
    "short_settled_funding" / FloatI80F48Adapter(),
    "open_orders" / PERP_OPEN_ORDERS,
    "liquidity_points" / FloatI80F48Adapter(),
)

# # 🥭 MANGO_ACCOUNT
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/state.rs):
# ```
# pub const MAX_NUM_IN_MARGIN_BASKET: u8 = 10;
# #[derive(Copy, Clone, Pod, Loadable)]
# #[repr(C)]
# pub struct MangoAccount {
#     pub meta_data: MetaData,
#
#     pub mango_group: Pubkey,
#     pub owner: Pubkey,
#
#     pub in_margin_basket: [bool; MAX_PAIRS],
#     pub num_in_margin_basket: u8,
#
#     // Spot and Margin related data
#     pub deposits: [I80F48; MAX_TOKENS],
#     pub borrows: [I80F48; MAX_TOKENS],
#     pub spot_open_orders: [Pubkey; MAX_PAIRS],
#
#     // Perps related data
#     pub perp_accounts: [PerpAccount; MAX_PAIRS],
#
#     pub msrm_amount: u64,
#     /// This account cannot open new positions or borrow until `init_health >= 0`
#     pub being_liquidated: bool,
#
#     /// This account cannot do anything except go through `resolve_bankruptcy`
#     pub is_bankrupt: bool,
#     pub padding: [u8; 6],
# }
# ```
MANGO_ACCOUNT = construct.Struct(
    "meta_data" / METADATA,
    "group" / PublicKeyAdapter(),
    "owner" / PublicKeyAdapter(),
    "in_margin_basket" / construct.Array(MAX_PAIRS, DecimalAdapter(1)),
    "num_in_margin_basket" / DecimalAdapter(1),
    "deposits" / construct.Array(MAX_TOKENS, FloatI80F48Adapter()),
    "borrows" / construct.Array(MAX_TOKENS, FloatI80F48Adapter()),
    "spot_open_orders" / construct.Array(MAX_PAIRS, PublicKeyAdapter()),
    "perp_accounts" / construct.Array(MAX_PAIRS, PERP_ACCOUNT),
    "msrm_amount" / DecimalAdapter(),
    "being_liquidated" / DecimalAdapter(1),
    "is_bankrupt" / DecimalAdapter(1),
    construct.Padding(6)
)


# # 🥭 PERP_MARKET
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/state.rs):
# ```
# /// This will hold top level info about the perps market
# /// Likely all perps transactions on a market will be locked on this one because this will be passed in as writable
# #[derive(Copy, Clone, Pod, Loadable, Default)]
# #[repr(C)]
# pub struct PerpMarket {
#     pub meta_data: MetaData,
#
#     pub mango_group: Pubkey,
#     pub bids: Pubkey,
#     pub asks: Pubkey,
#     pub event_queue: Pubkey,
#     pub quote_lot_size: i64, // number of quote native that reresents min tick
#     pub base_lot_size: i64,  // represents number of base native quantity; greater than 0
#
#     // TODO - consider just moving this into the cache
#     pub long_funding: I80F48,
#     pub short_funding: I80F48,
#
#     pub open_interest: i64, // This is i64 to keep consistent with the units of contracts, but should always be > 0
#
#     pub last_updated: u64,
#     pub seq_num: u64,
#     pub fees_accrued: I80F48, // native quote currency
#
#     // Liquidity incentive params
#     pub max_depth_bps: I80F48,
#     pub scaler: I80F48,
#     pub total_liquidity_points: I80F48,
#     pub points_per_mngo: I80F48, // how many points equal 1 native MNGO
#
#     // mngo_vault holds mango tokens to be disbursed as liquidity incentives for this perp market
#     pub mngo_vault: Pubkey,
# }
# ```
PERP_MARKET = construct.Struct(
    "meta_data" / METADATA,
    "group" / PublicKeyAdapter(),
    "bids" / PublicKeyAdapter(),
    "asks" / PublicKeyAdapter(),
    "event_queue" / PublicKeyAdapter(),
    "quote_lot_size" / SignedDecimalAdapter(),
    "base_lot_size" / SignedDecimalAdapter(),

    "long_funding" / FloatI80F48Adapter(),
    "short_funding" / FloatI80F48Adapter(),

    "open_interest" / SignedDecimalAdapter(),

    "last_updated" / DatetimeAdapter(),
    "seq_num" / DecimalAdapter(),
    "fees_accrued" / FloatI80F48Adapter(),

    "max_depth_bips" / FloatI80F48Adapter(),
    "scaler" / FloatI80F48Adapter(),
    "total_liquidity_points" / FloatI80F48Adapter(),
    "points_per_mngo" / FloatI80F48Adapter(),

    "mngo_vault" / PublicKeyAdapter()
)


# # 🥭 ANY_NODE
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/matching.rs):
# ```
# const NODE_SIZE: usize = 88;
# #[derive(Copy, Clone, Pod)]
# #[repr(C)]
# pub struct AnyNode {
#     pub tag: u32,
#     pub data: [u8; NODE_SIZE - 4],
# }
# ```
ANY_NODE = construct.Struct(
    "tag" / DecimalAdapter(4),
    "data" / construct.Bytes(_NODE_SIZE - 4)
)
assert ANY_NODE.sizeof() == _NODE_SIZE


# # 🥭 UNINITIALIZED_BOOK_NODE
#
# There is no Rust structure for this - it's just a blank node.
#
UNINITIALIZED_BOOK_NODE = construct.Struct(
    "type_name" / construct.Computed(lambda _: "uninitialized"),
    "tag" / construct.Const(Decimal(0), DecimalAdapter(4)),
    "data" / construct.Bytes(_NODE_SIZE - 4)
)
assert UNINITIALIZED_BOOK_NODE.sizeof() == ANY_NODE.sizeof()

# # 🥭 INNER_BOOK_NODE
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/matching.rs):
# ```
# #[derive(Copy, Clone, Pod)]
# #[repr(C)]
# pub struct InnerNode {
#     pub tag: u32,
#     pub prefix_len: u32,
#     pub key: i128,
#     pub children: [u32; 2],
#     pub padding: [u8; NODE_SIZE - 32],
# }
# ```
INNER_BOOK_NODE = construct.Struct(
    "type_name" / construct.Computed(lambda _: "inner"),
    "tag" / construct.Const(Decimal(1), DecimalAdapter(4)),
    # Only the first prefixLen high-order bits of key are meaningful
    "prefix_len" / DecimalAdapter(4),
    "key" / DecimalAdapter(16),
    "children" / construct.Array(2, DecimalAdapter(4)),
    "padding" / construct.Padding(_NODE_SIZE - 32)
)
assert INNER_BOOK_NODE.sizeof() == ANY_NODE.sizeof()

# # 🥭 LEAF_BOOK_NODE
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/matching.rs):
# ```
# #[derive(Debug, Copy, Clone, PartialEq, Eq, Pod)]
# #[repr(C)]
# pub struct LeafNode {
#     pub tag: u32,
#     pub owner_slot: u8,
#     pub padding: [u8; 3],
#     pub key: i128,
#     pub owner: Pubkey,
#     pub quantity: i64,
#     pub client_order_id: u64,
#
#     // Liquidity incentive related parameters
#     // Either the best bid or best ask at the time the order was placed
#     pub best_initial: i64,
#
#     // The time the order was place
#     pub timestamp: u64,
# }
# ```
LEAF_BOOK_NODE = construct.Struct(
    "type_name" / construct.Computed(lambda _: "leaf"),
    "tag" / construct.Const(Decimal(2), DecimalAdapter(4)),
    # Index into OPEN_ORDERS_LAYOUT.orders
    "owner_slot" / DecimalAdapter(1),
    "padding" / construct.Padding(3),
    # (price, seqNum)
    "key" / BookPriceAdapter(),
    "owner" / PublicKeyAdapter(),
    # In units of lot size
    "quantity" / DecimalAdapter(),
    "client_order_id" / DecimalAdapter(),

    "best_initial" / SignedDecimalAdapter(),
    "timestamp" / DatetimeAdapter()
)
assert LEAF_BOOK_NODE.sizeof() == ANY_NODE.sizeof()

# # 🥭 FREE_BOOK_NODE
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/matching.rs):
# ```
# #[derive(Copy, Clone, Pod)]
# #[repr(C)]
# struct FreeNode {
#     tag: u32,
#     next: u32,
#     padding: [u8; NODE_SIZE - 8],
# }
# ```
FREE_BOOK_NODE = construct.Struct(
    "type_name" / construct.Computed(lambda _: "free"),
    "tag" / construct.Const(Decimal(3), DecimalAdapter(4)),
    "next" / DecimalAdapter(4),
    "padding" / construct.Padding(_NODE_SIZE - 8)
)
assert FREE_BOOK_NODE.sizeof() == ANY_NODE.sizeof()

# # 🥭 FREE_BOOK_NODE
#
# Last Free Node is identical to free node, apart from the tag.
#
LAST_FREE_BOOK_NODE = construct.Struct(
    "type_name" / construct.Computed(lambda _: "last_free"),
    "tag" / construct.Const(Decimal(4), DecimalAdapter(4)),
    "next" / DecimalAdapter(4),
    "padding" / construct.Padding(_NODE_SIZE - 8)
)
assert LAST_FREE_BOOK_NODE.sizeof() == ANY_NODE.sizeof()


# # 🥭 ORDERBOOK_SIDE
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/matching.rs):
# ```
# pub const MAX_BOOK_NODES: usize = 1024; // NOTE: this cannot be larger than u32::MAX
#
# #[derive(Copy, Clone, Pod, Loadable)]
# #[repr(C)]
# pub struct BookSide {
#     pub meta_data: MetaData,
#
#     pub bump_index: usize,
#     pub free_list_len: usize,
#     pub free_list_head: u32,
#     pub root_node: u32,
#     pub leaf_count: usize,
#     pub nodes: [AnyNode; MAX_BOOK_NODES], // TODO make this variable length
# }
# ```
ORDERBOOK_SIDE = construct.Struct(
    "meta_data" / METADATA,
    "bump_index" / DecimalAdapter(),
    "free_list_len" / DecimalAdapter(),
    "free_list_head" / DecimalAdapter(4),
    "root_node" / DecimalAdapter(4),
    "leaf_count" / DecimalAdapter(),
    "nodes" / construct.Array(MAX_BOOK_NODES, OrderBookNodeAdapter())
)


# # 🥭 FILL_EVENT
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/queue.rs):
# ```
# const EVENT_SIZE: usize = 152;
# #[derive(Copy, Clone, Debug, Pod)]
# #[repr(C)]
# pub struct FillEvent {
#     pub event_type: u8,
#     pub side: Side, // side from the taker's POV
#     pub maker_slot: u8,
#     pub maker_out: bool, // true if maker order quantity == 0
#     pub padding: [u8; 4],
#     pub maker: Pubkey,
#     pub maker_order_id: i128,
#     pub maker_client_order_id: u64,
#
#     // The best bid/ask at the time the maker order was placed. Used for liquidity incentives
#     pub best_initial: i64,
#
#     // Timestamp of when the maker order was placed; copied over from the LeafNode
#     pub timestamp: u64,
#
#     pub taker: Pubkey,
#     pub taker_order_id: i128,
#     pub taker_client_order_id: u64,
#
#     pub price: i64,
#     pub quantity: i64, // number of quote lots
# }
# ```
FILL_EVENT = construct.Struct(
    "event_type" / construct.Const(b'\x00'),
    "side" / DecimalAdapter(1),
    "maker_slot" / DecimalAdapter(1),
    "maker_out" / construct.Flag,
    construct.Padding(4),
    "maker" / PublicKeyAdapter(),
    "maker_order_id" / SignedDecimalAdapter(16),
    "maker_client_order_id" / DecimalAdapter(),

    "best_initial" / SignedDecimalAdapter(),

    "timestamp" / DatetimeAdapter(),

    "taker" / PublicKeyAdapter(),
    "taker_order_id" / SignedDecimalAdapter(16),
    "taker_client_order_id" / DecimalAdapter(),

    "price" / SignedDecimalAdapter(),
    "quantity" / SignedDecimalAdapter()
)
_EVENT_SIZE = 152
assert FILL_EVENT.sizeof() == _EVENT_SIZE

# # 🥭 OUT_EVENT
#
# Here's the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/queue.rs):
# ```
# #[derive(Copy, Clone, Debug, Pod)]
# #[repr(C)]
# pub struct OutEvent {
#     pub event_type: u8,
#     pub side: Side,
#     pub slot: u8,
#     padding0: [u8; 5],
#     pub owner: Pubkey,
#     pub quantity: i64,
#     padding1: [u8; EVENT_SIZE - 48],
# }
# ```
OUT_EVENT = construct.Struct(
    "event_type" / construct.Const(b'\x01'),
    "side" / DecimalAdapter(1),
    "slot" / DecimalAdapter(1),
    construct.Padding(5),
    "owner" / PublicKeyAdapter(),
    "quantity" / SignedDecimalAdapter(),
    construct.Padding(_EVENT_SIZE - 48)
)
assert OUT_EVENT.sizeof() == _EVENT_SIZE

UNKNOWN_EVENT = construct.Struct(
    "event_type" / construct.Bytes(1),
    construct.Padding(7),
    "owner" / PublicKeyAdapter(),
    construct.Padding(_EVENT_SIZE - 40)
)
assert UNKNOWN_EVENT.sizeof() == _EVENT_SIZE

# # 🥭 PERP_EVENT_QUEUE
#
# The event queue is handled a little differently. The idea is that there's some header data and then a ring
# buffer of events. These events are overwritten as new events come in. Each event has the same fixed size, so
# it's straightforward to offset into the ring buffer if you know the index.
#
# Here's some of the [Rust structure](https://github.com/blockworks-foundation/mango-v3/blob/main/program/src/queue.rs):
# ```
# # #[derive(Copy, Clone, Pod)]
# #[repr(C)]
# pub struct EventQueueHeader {
#     pub meta_data: MetaData,
#     head: usize,
#     count: usize,
#     seq_num: usize,
# }
# ```
PERP_EVENT_QUEUE = construct.Struct(
    "meta_data" / METADATA,
    "head" / DecimalAdapter(),
    "count" / DecimalAdapter(),
    "seq_num" / DecimalAdapter(),
    "events" / construct.RepeatUntil(lambda obj, lst, ctx: len(lst) == ctx["seq_num"],
                                     construct.Select(FILL_EVENT, OUT_EVENT, UNKNOWN_EVENT))
    # "events" / construct.GreedyRange(FILL_EVENT)
)

# # Instruction Structs

# ## MANGO_INSTRUCTION_VARIANT_FINDER
#
# The 'variant' of the instruction is held in the first 4 bytes. The remainder of the data
# is per-instruction.
#
# This `struct` loads only the first 4 bytes, as an `int`, so we know which specific parser
# has to be used to load the rest of the data.


MANGO_INSTRUCTION_VARIANT_FINDER = construct.Struct(
    "variant" / construct.BytesInteger(4, swapped=True)
)

# /// Place an order on a perp market
# /// Accounts expected by this instruction (6):
# /// 0. `[]` mango_group_ai - TODO
# /// 1. `[writable]` mango_account_ai - TODO
# /// 2. `[signer]` owner_ai - TODO
# /// 3. `[]` mango_cache_ai - TODO
# /// 4. `[writable]` perp_market_ai - TODO
# /// 5. `[writable]` bids_ai - TODO
# /// 6. `[writable]` asks_ai - TODO
# /// 7. `[writable]` event_queue_ai - TODO
PLACE_PERP_ORDER = construct.Struct(
    "variant" / construct.Const(12, construct.BytesInteger(4, swapped=True)),

    "price" / SignedDecimalAdapter(),
    "quantity" / SignedDecimalAdapter(),
    "client_order_id" / DecimalAdapter(),
    "side" / DecimalAdapter(1),  # { buy: 0, sell: 1 }
    "order_type" / DecimalAdapter(1)  # { limit: 0, ioc: 1, postOnly: 2 }
)

# /// Initialize a Mango account for a user
# ///
# /// Accounts expected by this instruction (4):
# ///
# /// 0. `[]` mango_group_ai - MangoGroup that this mango account is for
# /// 1. `[writable]` mango_account_ai - the mango account data
# /// 2. `[signer]` owner_ai - Solana account of owner of the mango account
# /// 3. `[]` rent_ai - Rent sysvar account
# InitMangoAccount,
INIT_MANGO_ACCOUNT = construct.Struct(
    "variant" / construct.Const(1, construct.BytesInteger(4, swapped=True))
)


# Cancel a Perp order using it's ID and Side.
#
# 0. `[]` mangoGroupPk
# 1. `[writable]` mangoAccountPk
# 2. `[signer]` ownerPk
# 3. `[writable]` perpMarketPk
# 4. `[writable]` bidsPk
# 5. `[writable]` asksPk
# 6. `[writable]` eventQueuePk
CANCEL_PERP_ORDER = construct.Struct(
    "variant" / construct.Const(14, construct.BytesInteger(4, swapped=True)),

    "order_id" / DecimalAdapter(16),
    "side" / DecimalAdapter(4)  # { buy: 0, sell: 1 }
)


# /// Deposit funds into mango account
# ///
# /// Accounts expected by this instruction (8):
# ///
# /// 0. `[]` mango_group_ai - MangoGroup that this mango account is for
# /// 1. `[writable]` mango_account_ai - the mango account for this user
# /// 2. `[signer]` owner_ai - Solana account of owner of the mango account
# /// 3. `[]` mango_cache_ai - MangoCache
# /// 4. `[]` root_bank_ai - RootBank owned by MangoGroup
# /// 5. `[writable]` node_bank_ai - NodeBank owned by RootBank
# /// 6. `[writable]` vault_ai - TokenAccount owned by MangoGroup
# /// 7. `[]` token_prog_ai - acc pointed to by SPL token program id
# /// 8. `[writable]` owner_token_account_ai - TokenAccount owned by user which will be sending the funds
# Deposit {
#     quantity: u64,
# },
DEPOSIT = construct.Struct(
    "variant" / construct.Const(2, construct.BytesInteger(4, swapped=True)),

    "quantity" / DecimalAdapter()
)


# /// Withdraw funds that were deposited earlier.
# ///
# /// Accounts expected by this instruction (10):
# ///
# /// 0. `[read]` mango_group_ai,   -
# /// 1. `[write]` mango_account_ai, -
# /// 2. `[read]` owner_ai,         -
# /// 3. `[read]` mango_cache_ai,   -
# /// 4. `[read]` root_bank_ai,     -
# /// 5. `[write]` node_bank_ai,     -
# /// 6. `[write]` vault_ai,         -
# /// 7. `[write]` token_account_ai, -
# /// 8. `[read]` signer_ai,        -
# /// 9. `[read]` token_prog_ai,    -
# /// 10. `[read]` clock_ai,         -
# /// 11..+ `[]` open_orders_accs - open orders for each of the spot market
# Withdraw {
#     quantity: u64,
#     allow_borrow: bool,
# },
WITHDRAW = construct.Struct(
    "variant" / construct.Const(3, construct.BytesInteger(4, swapped=True)),

    "quantity" / DecimalAdapter(),
    "allow_borrow" / DecimalAdapter(1)
)


# /// Place an order on the Serum Dex using Mango account
# /// Accounts expected by this instruction (22+openorders):
# { isSigner: false, isWritable: false, pubkey: mangoGroupPk },
# { isSigner: false, isWritable: true, pubkey: mangoAccountPk },
# { isSigner: true, isWritable: false, pubkey: ownerPk },
# { isSigner: false, isWritable: false, pubkey: mangoCachePk },
# { isSigner: false, isWritable: false, pubkey: serumDexPk },
# { isSigner: false, isWritable: true, pubkey: spotMarketPk },
# { isSigner: false, isWritable: true, pubkey: bidsPk },
# { isSigner: false, isWritable: true, pubkey: asksPk },
# { isSigner: false, isWritable: true, pubkey: requestQueuePk },
# { isSigner: false, isWritable: true, pubkey: eventQueuePk },
# { isSigner: false, isWritable: true, pubkey: spotMktBaseVaultPk },
# { isSigner: false, isWritable: true, pubkey: spotMktQuoteVaultPk },
# { isSigner: false, isWritable: false, pubkey: baseRootBankPk },
# { isSigner: false, isWritable: true, pubkey: baseNodeBankPk },
# { isSigner: false, isWritable: true, pubkey: quoteRootBankPk },
# { isSigner: false, isWritable: true, pubkey: quoteNodeBankPk },
# { isSigner: false, isWritable: true, pubkey: quoteVaultPk },
# { isSigner: false, isWritable: true, pubkey: baseVaultPk },
# { isSigner: false, isWritable: false, pubkey: TOKEN_PROGRAM_ID },
# { isSigner: false, isWritable: false, pubkey: signerPk },
# { isSigner: false, isWritable: false, pubkey: SYSVAR_RENT_PUBKEY },
# { isSigner: false, isWritable: false, pubkey: dexSignerPk },
# ...openOrders.map((pubkey) => ({
#   isSigner: false,
#   isWritable: true, // TODO: only pass the one writable you are going to place the order on
#   pubkey,
# })),
PLACE_SPOT_ORDER = construct.Struct(
    "variant" / construct.Const(9, construct.BytesInteger(4, swapped=True)),  # 4

    'side' / DecimalAdapter(4),  # 8
    "limit_price" / DecimalAdapter(),  # 16
    'max_base_quantity' / DecimalAdapter(),  # 24
    'max_quote_quantity' / DecimalAdapter(),  # 32
    'self_trade_behavior' / DecimalAdapter(4),  # 36
    'order_type' / DecimalAdapter(4),  # 40
    'client_id' / DecimalAdapter(),  # 48
    'limit' / DecimalAdapter(2),  # 50
)

# /// Cancel an order using dex instruction
# ///
# /// Accounts expected by this instruction ():
# ///
# CancelSpotOrder {
#     order: serum_dex::instruction::CancelOrderInstructionV2,
# },
CANCEL_SPOT_ORDER = construct.Struct(
    "variant" / construct.Const(20, construct.BytesInteger(4, swapped=True)),

    'side' / DecimalAdapter(4),
    "order_id" / DecimalAdapter(16)
)


# Cancel a Perp order using only it's client ID.
#
# 0. `[]` mangoGroupPk
# 1. `[writable]` mangoAccountPk
# 2. `[signer]` ownerPk
# 3. `[writable]` perpMarketPk
# 4. `[writable]` bidsPk
# 5. `[writable]` asksPk
# 6. `[writable]` eventQueuePk
CANCEL_PERP_ORDER_BY_CLIENT_ID = construct.Struct(
    "variant" / construct.Const(13, construct.BytesInteger(4, swapped=True)),

    "client_order_id" / DecimalAdapter()
)

# Run the Mango crank.
#
# 0. `[]` mangoGroupPk
# 1. `[]` perpMarketPk
# 2. `[writable]` eventQueuePk
# 3+ `[writable]` mangoAccountPks...
CONSUME_EVENTS = construct.Struct(
    "variant" / construct.Const(15, construct.BytesInteger(4, swapped=True)),

    "limit" / DecimalAdapter()
)

# /// Settle all funds from serum dex open orders
# ///
# /// Accounts expected by this instruction (18):
# ///
# /// 0. `[]` mango_group_ai - MangoGroup that this mango account is for
# /// 1. `[]` mango_cache_ai - MangoCache for this MangoGroup
# /// 2. `[signer]` owner_ai - MangoAccount owner
# /// 3. `[writable]` mango_account_ai - MangoAccount
# /// 4. `[]` dex_prog_ai - program id of serum dex
# /// 5.  `[writable]` spot_market_ai - dex MarketState account
# /// 6.  `[writable]` open_orders_ai - open orders for this market for this MangoAccount
# /// 7. `[]` signer_ai - MangoGroup signer key
# /// 8. `[writable]` dex_base_ai - base vault for dex MarketState
# /// 9. `[writable]` dex_quote_ai - quote vault for dex MarketState
# /// 10. `[]` base_root_bank_ai - MangoGroup base vault acc
# /// 11. `[writable]` base_node_bank_ai - MangoGroup quote vault acc
# /// 12. `[]` quote_root_bank_ai - MangoGroup quote vault acc
# /// 13. `[writable]` quote_node_bank_ai - MangoGroup quote vault acc
# /// 14. `[writable]` base_vault_ai - MangoGroup base vault acc
# /// 15. `[writable]` quote_vault_ai - MangoGroup quote vault acc
# /// 16. `[]` dex_signer_ai - dex Market signer account
# /// 17. `[]` spl token program
SETTLE_FUNDS = construct.Struct(
    "variant" / construct.Const(19, construct.BytesInteger(4, swapped=True))
)

InstructionParsersByVariant = {
    0: None,  # INIT_MANGO_GROUP,
    1: INIT_MANGO_ACCOUNT,  # INIT_MANGO_ACCOUNT,
    2: DEPOSIT,  # DEPOSIT,
    3: WITHDRAW,  # WITHDRAW,
    4: None,  # ADD_SPOT_MARKET,
    5: None,  # ADD_TO_BASKET,
    6: None,  # BORROW,
    7: None,  # CACHE_PRICES,
    8: None,  # CACHE_ROOT_BANKS,
    9: PLACE_SPOT_ORDER,  # PLACE_SPOT_ORDER,
    10: None,  # ADD_ORACLE,
    11: None,  # ADD_PERP_MARKET,
    12: PLACE_PERP_ORDER,  # PLACE_PERP_ORDER,
    13: CANCEL_PERP_ORDER_BY_CLIENT_ID,  # CANCEL_PERP_ORDER_BY_CLIENT_ID,
    14: CANCEL_PERP_ORDER,  # CANCEL_PERP_ORDER,
    15: CONSUME_EVENTS,  # CONSUME_EVENTS,
    16: None,  # CACHE_PERP_MARKETS,
    17: None,  # UPDATE_FUNDING,
    18: None,  # SET_ORACLE,
    19: SETTLE_FUNDS,  # SETTLE_FUNDS,
    20: CANCEL_SPOT_ORDER,  # CANCEL_SPOT_ORDER,
    21: None,  # UPDATE_ROOT_BANK,
    22: None,  # SETTLE_PNL,
    23: None,  # SETTLE_BORROW,
}
