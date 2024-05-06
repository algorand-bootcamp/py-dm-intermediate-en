import base64
import functools

import algokit_utils
import algosdk
import pytest
from algokit_utils.beta.account_manager import AddressAndSigner
from algokit_utils.beta.algorand_client import (
    AlgorandClient,
    AssetCreateParams,
    PayParams,
)
from algokit_utils.beta.composer import AssetTransferParams
from algokit_utils.config import config
from algosdk.atomic_transaction_composer import TransactionWithSigner
from algosdk.transaction import (
    wait_for_confirmation,
)

from smart_contracts.artifacts.digital_marketplace.client import (
    DigitalMarketplaceClient,
)

FOR_SALE_MBR = 2_500 + 64 * 400


@pytest.fixture(scope="session")
def dispenser(algorand_client: AlgorandClient) -> AddressAndSigner:
    return algorand_client.account.dispenser()


@pytest.fixture(scope="session")
def creator(
    algorand_client: AlgorandClient, dispenser: AddressAndSigner
) -> AddressAndSigner:
    acct = algorand_client.account.random()

    algorand_client.send.payment(
        PayParams(sender=dispenser.address, receiver=acct.address, amount=10_000_000)
    )

    return acct


@pytest.fixture(scope="session")
def test_assets_id(
    creator: AddressAndSigner, algorand_client: AlgorandClient
) -> (int, int):
    return (
        algorand_client.send.asset_create(
            AssetCreateParams(sender=creator.address, total=10_000, decimals=3)
        )["confirmation"]["asset-index"],
        algorand_client.send.asset_create(
            AssetCreateParams(sender=creator.address, total=10_000, decimals=3)
        )["confirmation"]["asset-index"],
    )


@pytest.fixture(scope="session")
def buyer(
    algorand_client: AlgorandClient,
    dispenser: AddressAndSigner,
    test_assets_id: (int, int),
) -> AddressAndSigner:
    acct = algorand_client.account.random()

    algorand_client.send.payment(
        PayParams(sender=dispenser.address, receiver=acct.address, amount=100_000_000)
    )

    for asset_id in test_assets_id:
        wait_for_confirmation(
            algorand_client.client.algod,
            algorand_client.client.algod.send_transaction(
                acct.signer.sign_transactions(
                    [
                        algorand_client.transactions.asset_transfer(
                            AssetTransferParams(
                                asset_id=asset_id,
                                sender=acct.address,
                                receiver=acct.address,
                                amount=0,
                            )
                        )
                    ],
                    indexes=[0],
                )[0]
            ),
        )

    return acct


@pytest.fixture(scope="session")
def digital_marketplace_client(
    creator: AddressAndSigner,
    algorand_client: AlgorandClient,
) -> DigitalMarketplaceClient:
    config.configure(
        debug=True,
        # trace_all=True,
    )

    client = DigitalMarketplaceClient(
        algorand_client.client.algod,
        creator=creator.address,
        signer=creator.signer,
        indexer_client=algorand_client.client.indexer,
    )

    # client.deploy(
    #     on_schema_break=algokit_utils.OnSchemaBreak.AppendApp,
    #     on_update=algokit_utils.OnUpdate.AppendApp,
    # )
    client.create_bare()
    algokit_utils.ensure_funded(
        algorand_client.client.algod,
        algokit_utils.EnsureBalanceParameters(
            account_to_fund=client.app_address, min_spending_balance_micro_algos=0
        ),
    )
    return client


def test_allow_asset(
    algorand_client: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: AddressAndSigner,
    test_assets_id: (int, int),
) -> None:
    for asset_id in test_assets_id:
        pytest.raises(
            algosdk.error.AlgodHTTPError,
            functools.partial(
                algorand_client.client.algod.account_asset_info,
                digital_marketplace_client.app_address,
                asset_id,
            ),
        )

        result = digital_marketplace_client.allow_asset(
            mbr_pay=TransactionWithSigner(
                algorand_client.transactions.payment(
                    PayParams(
                        sender=creator.address,
                        receiver=digital_marketplace_client.app_address,
                        amount=100_000,
                        extra_fee=1_000,
                    )
                ),
                signer=creator.signer,
            ),
            asset=asset_id,
        )

        assert result.confirmed_round

        assert (
            digital_marketplace_client.algod_client.account_asset_info(
                digital_marketplace_client.app_address, asset_id
            )["asset-holding"]["amount"]
            == 0
        )


def test_first_deposit(
    algorand_client: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: AddressAndSigner,
    test_assets_id: (int, int),
) -> None:
    for asset_id in test_assets_id:
        box_key = (
            algosdk.encoding.decode_address(creator.address)
            + algosdk.encoding.encode_as_bytes(asset_id)
            + algosdk.encoding.encode_as_bytes(0)
        )

        result = digital_marketplace_client.first_deposit(
            mbr_pay=TransactionWithSigner(
                algorand_client.transactions.payment(
                    PayParams(
                        sender=creator.address,
                        receiver=digital_marketplace_client.app_address,
                        amount=FOR_SALE_MBR,
                        extra_fee=1_000,
                    )
                ),
                creator.signer,
            ),
            xfer=TransactionWithSigner(
                algorand_client.transactions.asset_transfer(
                    AssetTransferParams(
                        asset_id=asset_id,
                        sender=creator.address,
                        receiver=digital_marketplace_client.app_address,
                        amount=3_000,
                    )
                ),
                creator.signer,
            ),
            nonce=0,
            unitary_price=1_000_000,
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)]
            ),
        )

        assert result.confirmed_round

        box_content = algorand_client.client.algod.application_box_by_name(
            digital_marketplace_client.app_id,
            box_key,
        )["value"]
        decoded_box_content = base64.b64decode(box_content)
        assert int.from_bytes(decoded_box_content[:8], "big") == 3_000
        assert int.from_bytes(decoded_box_content[8:16], "big") == 1_000_000


def test_deposit(
    algorand_client: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: AddressAndSigner,
    test_assets_id: (int, int),
) -> None:
    for asset_id in test_assets_id:
        box_key = (
            algosdk.encoding.decode_address(creator.address)
            + algosdk.encoding.encode_as_bytes(asset_id)
            + algosdk.encoding.encode_as_bytes(0)
        )

        result = digital_marketplace_client.deposit(
            xfer=TransactionWithSigner(
                algorand_client.transactions.asset_transfer(
                    AssetTransferParams(
                        asset_id=asset_id,
                        sender=creator.address,
                        receiver=digital_marketplace_client.app_address,
                        amount=1_000,
                        extra_fee=1_000,
                    )
                ),
                creator.signer,
            ),
            nonce=0,
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)]
            ),
        )

        assert result.confirmed_round

        box_content = algorand_client.client.algod.application_box_by_name(
            digital_marketplace_client.app_id,
            box_key,
        )["value"]
        decoded_box_content = base64.b64decode(box_content)
        assert int.from_bytes(decoded_box_content[:8], "big") == 4_000
        assert int.from_bytes(decoded_box_content[8:16], "big") == 1_000_000


def test_set_price(
    algorand_client: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: AddressAndSigner,
    test_assets_id: (int, int),
) -> None:
    for asset_id, unitary_price in zip(test_assets_id, [3_200_000, 5_700_000]):
        box_key = (
            algosdk.encoding.decode_address(creator.address)
            + algosdk.encoding.encode_as_bytes(asset_id)
            + algosdk.encoding.encode_as_bytes(0)
        )

        result = digital_marketplace_client.set_price(
            asset=asset_id,
            nonce=0,
            unitary_price=unitary_price,
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)]
            ),
        )

        assert result.confirmed_round

        box_content = algorand_client.client.algod.application_box_by_name(
            digital_marketplace_client.app_id,
            box_key,
        )["value"]
        assert (
            int.from_bytes(base64.b64decode(box_content)[8:16], "big") == unitary_price
        )


def test_buy(
    algorand_client: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    buyer: AddressAndSigner,
    creator: AddressAndSigner,
    test_assets_id: (int, int),
) -> None:
    for asset_id, amount_to_pay in zip(test_assets_id, [6_793_600, 12_101_100]):
        box_key = (
            algosdk.encoding.decode_address(creator.address)
            + algosdk.encoding.encode_as_bytes(asset_id)
            + algosdk.encoding.encode_as_bytes(0)
        )

        result = digital_marketplace_client.buy(
            owner=creator.address,
            asset=asset_id,
            nonce=0,
            buy_pay=TransactionWithSigner(
                algorand_client.transactions.payment(
                    PayParams(
                        sender=buyer.address,
                        receiver=creator.address,
                        amount=amount_to_pay,
                        extra_fee=1_000,
                    )
                ),
                buyer.signer,
            ),
            quantity=2_123,
            transaction_parameters=algokit_utils.TransactionParameters(
                sender=buyer.address,
                signer=buyer.signer,
                boxes=[(0, box_key)],
            ),
        )

        assert result.confirmed_round

        assert (
            algorand_client.client.algod.account_asset_info(buyer.address, asset_id)[
                "asset-holding"
            ]["amount"]
            == 2_123
        )


def test_withdraw(
    algorand_client: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: AddressAndSigner,
    test_assets_id: (int, int),
) -> None:
    for asset_id in test_assets_id:
        box_key = (
            algosdk.encoding.decode_address(creator.address)
            + algosdk.encoding.encode_as_bytes(asset_id)
            + algosdk.encoding.encode_as_bytes(0)
        )

        before_call_amount = algorand_client.client.algod.account_info(creator.address)[
            "amount"
        ]

        sp = algorand_client.client.algod.suggested_params()
        sp.flat_fee = True
        sp.fee = 3_000
        result = digital_marketplace_client.withdraw(
            asset=asset_id,
            nonce=0,
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)], suggested_params=sp
            ),
        )

        assert result.confirmed_round

        after_call_amount = algorand_client.client.algod.account_info(creator.address)[
            "amount"
        ]

        assert after_call_amount - before_call_amount == FOR_SALE_MBR - 3_000
        assert (
            algorand_client.client.algod.account_asset_info(creator.address, asset_id)[
                "asset-holding"
            ]["amount"]
            == 7_877
        )
