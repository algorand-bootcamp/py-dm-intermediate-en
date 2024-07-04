# pyright: reportMissingModuleSource=false

from algopy import (
    Asset,
    BoxMap,
    Global,
    Txn,
    UInt64,
    arc4,
    gtxn,
    itxn,
    op,
    subroutine,
)

FOR_SALE_BOX_KEY_LENGTH = 8 + 48
FOR_SALE_BOX_VALUE_LENGTH = 64
FOR_SALE_BOX_SIZE = FOR_SALE_BOX_KEY_LENGTH + FOR_SALE_BOX_VALUE_LENGTH
FOR_SALE_BOX_MBR = 2_500 + FOR_SALE_BOX_SIZE * 400


class ListingKey(arc4.Struct):
    owner: arc4.Address
    asset: arc4.UInt64
    nonce: arc4.UInt64


class ListingValue(arc4.Struct):
    deposited: arc4.UInt64
    unitary_price: arc4.UInt64
    bidder: arc4.Address
    bid: arc4.UInt64
    bid_unitary_price: arc4.UInt64


class DigitalMarketplace(arc4.ARC4Contract):
    def __init__(self) -> None:
        self.listings = BoxMap(ListingKey, ListingValue)

    @subroutine
    def quantity_price(
        self, quantity: UInt64, price: UInt64, asset_decimals: UInt64
    ) -> UInt64:
        amount_not_scaled_high, amount_not_scaled_low = op.mulw(price, quantity)
        scaling_factor_high, scaling_factor_low = op.expw(10, asset_decimals)
        _quotient_high, amount_to_be_paid, _remainder_high, _remainder_low = op.divmodw(
            amount_not_scaled_high,
            amount_not_scaled_low,
            scaling_factor_high,
            scaling_factor_low,
        )
        assert not _quotient_high

        return amount_to_be_paid

    @arc4.abimethod
    def allow_asset(self, mbr_pay: gtxn.PaymentTransaction, asset: Asset) -> None:
        assert not Global.current_application_address.is_opted_in(asset)

        assert mbr_pay.receiver == Global.current_application_address
        assert mbr_pay.amount == Global.asset_opt_in_min_balance

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Global.current_application_address,
            asset_amount=0,
        ).submit()

    @arc4.abimethod
    def first_deposit(
        self,
        mbr_pay: gtxn.PaymentTransaction,
        xfer: gtxn.AssetTransferTransaction,
        nonce: arc4.UInt64,
        unitary_price: arc4.UInt64,
    ) -> None:
        assert mbr_pay.sender == Txn.sender
        assert mbr_pay.receiver == Global.current_application_address
        assert mbr_pay.amount == FOR_SALE_BOX_MBR

        key = ListingKey(
            arc4.Address(Txn.sender), arc4.UInt64(xfer.xfer_asset.id), nonce
        )
        assert key not in self.listings

        assert xfer.sender == Txn.sender
        assert xfer.asset_receiver == Global.current_application_address
        assert xfer.asset_amount > 0

        self.listings[key] = ListingValue(
            arc4.UInt64(xfer.asset_amount),
            unitary_price,
            arc4.Address(),
            arc4.UInt64(),
            arc4.UInt64(),
        )

    @arc4.abimethod
    def deposit(self, xfer: gtxn.AssetTransferTransaction, nonce: arc4.UInt64) -> None:
        key = ListingKey(
            arc4.Address(Txn.sender), arc4.UInt64(xfer.xfer_asset.id), nonce
        )

        assert xfer.sender == Txn.sender
        assert xfer.asset_receiver == Global.current_application_address
        assert xfer.asset_amount > 0

        self.listings[key].deposited = arc4.UInt64(
            self.listings[key].deposited.native + xfer.asset_amount
        )

    @arc4.abimethod
    def set_price(
        self, asset: UInt64, nonce: arc4.UInt64, unitary_price: arc4.UInt64
    ) -> None:
        key = ListingKey(arc4.Address(Txn.sender), arc4.UInt64(asset), nonce)

        self.listings[key].unitary_price = unitary_price

    @arc4.abimethod
    def withdraw(self, asset: Asset, nonce: arc4.UInt64) -> None:
        key = ListingKey(arc4.Address(Txn.sender), arc4.UInt64(asset.id), nonce)

        listing = self.listings[key].copy()
        if listing.bidder != arc4.Address():
            current_bid_deposit = self.quantity_price(
                listing.bid.native,
                listing.bid_unitary_price.native,
                asset.decimals,
            )
            itxn.Payment(
                receiver=listing.bidder.native, amount=current_bid_deposit
            ).submit()

        del self.listings[key]

        itxn.Payment(receiver=Txn.sender, amount=FOR_SALE_BOX_MBR).submit()

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Txn.sender,
            asset_amount=listing.deposited.native,
        ).submit()

    @arc4.abimethod
    def buy(
        self,
        owner: arc4.Address,
        asset: Asset,
        nonce: arc4.UInt64,
        buy_pay: gtxn.PaymentTransaction,
        quantity: UInt64,
    ) -> None:
        key = ListingKey(owner, arc4.UInt64(asset.id), nonce)

        listing = self.listings[key].copy()
        amount_to_be_paid = self.quantity_price(
            quantity, listing.unitary_price.native, asset.decimals
        )

        assert buy_pay.sender == Txn.sender
        assert buy_pay.receiver.bytes == owner.bytes
        assert buy_pay.amount == amount_to_be_paid

        self.listings[key].deposited = arc4.UInt64(listing.deposited.native - quantity)

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Txn.sender,
            asset_amount=quantity,
        ).submit()

    @arc4.abimethod
    def bid(
        self,
        owner: arc4.Address,
        asset: Asset,
        nonce: arc4.UInt64,
        bid_pay: gtxn.PaymentTransaction,
        quantity: arc4.UInt64,
        unitary_price: arc4.UInt64,
    ) -> None:
        assert Txn.sender.is_opted_in(asset)

        key = ListingKey(owner, arc4.UInt64(asset.id), nonce)

        listing = self.listings[key].copy()
        if listing.bidder != arc4.Address():
            assert unitary_price > listing.bid_unitary_price

            current_bid_amount = self.quantity_price(
                listing.bid.native, listing.bid_unitary_price.native, asset.decimals
            )

            itxn.Payment(
                receiver=listing.bidder.native, amount=current_bid_amount
            ).submit()

        amount_to_be_bid = self.quantity_price(
            quantity.native, unitary_price.native, asset.decimals
        )

        assert bid_pay.sender == Txn.sender
        assert bid_pay.receiver == Global.current_application_address
        assert bid_pay.amount == amount_to_be_bid

        self.listings[key].bidder = arc4.Address(Txn.sender)
        self.listings[key].bid = quantity
        self.listings[key].bid_unitary_price = unitary_price

    @arc4.abimethod
    def accept_bid(self, asset: Asset, nonce: arc4.UInt64) -> None:
        key = ListingKey(arc4.Address(Txn.sender), arc4.UInt64(asset.id), nonce)

        listing = self.listings[key].copy()
        assert listing.bidder != arc4.Address()

        min_quantity = (
            listing.deposited.native
            if listing.deposited.native < listing.bid.native
            else listing.bid.native
        )
        best_bid_amount = self.quantity_price(
            min_quantity, listing.bid_unitary_price.native, asset.decimals
        )

        itxn.Payment(receiver=Txn.sender, amount=best_bid_amount).submit()

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=listing.bidder.native,
            asset_amount=min_quantity,
        ).submit()

        self.listings[key].deposited = arc4.UInt64(
            self.listings[key].deposited.native - min_quantity
        )
        self.listings[key].bid = arc4.UInt64(
            self.listings[key].bid.native - min_quantity
        )

    # HOMEWORK: Write a way for the bidder to retract his bid without waiting for "accept_bid" or "withdraw"
